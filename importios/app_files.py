"""USB access to shared Documents folders of installed iOS apps via house_arrest."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid

from .cancellation import CURRENT, TransferCancelled, checkpoint
from .library import LibraryError, connection_failure
from .models import text_key

DOCUMENTS_ROOT = '/Documents'
CHUNK = 1024 * 1024
MAX_FILE_BYTES = 4 * 1024**3
MAX_ENTRIES = 10_000
MAX_UPLOAD_FILES = 2_000
MAX_FOLDERS = 500
MAX_NAME_BYTES = 255
TEMP_PREFIX = '.tupaq-tmp-'
BUNDLE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$')


class AppFilesError(LibraryError):
    pass


def validate_bundle_id(bundle_id):
    if not isinstance(bundle_id, str) or not BUNDLE_RE.fullmatch(bundle_id) or '..' in bundle_id or bundle_id.endswith('.'):
        raise AppFilesError('El identificador de la aplicación no es válido.', 'app-files:bundle-id')
    return bundle_id


def validate_name(name):
    if not isinstance(name, str) or not name or not name.strip():
        raise AppFilesError('El nombre del archivo o carpeta no es válido.', 'app-files:name')
    if name in ('.', '..') or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        raise AppFilesError('El nombre contiene caracteres no permitidos.', 'app-files:name')
    if len(name.encode('utf-8')) > MAX_NAME_BYTES:
        raise AppFilesError('El nombre supera el límite de 255 bytes.', 'app-files:name-length')
    return name


def normalize_relative(relative=''):
    if relative is None or relative == '' or relative == '/':
        return ''
    if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
        raise AppFilesError('La ruta dentro de la aplicación no es válida.', 'app-files:path')
    parts = [part for part in relative.strip('/').split('/') if part]
    for part in parts:
        validate_name(part)
    return '/'.join(parts)


def documents_path(relative=''):
    clean = normalize_relative(relative)
    return f'{DOCUMENTS_ROOT}/{clean}' if clean else DOCUMENTS_ROOT


def parent_relative(relative=''):
    clean = normalize_relative(relative)
    return clean.rpartition('/')[0] if '/' in clean else ''


def _child_relative(relative, name):
    clean = normalize_relative(relative)
    valid = validate_name(name)
    return f'{clean}/{valid}' if clean else valid


def _not_found_types():
    try:
        from pymobiledevice3.services.afc import AfcFileNotFoundError
        return (FileNotFoundError, AfcFileNotFoundError)
    except Exception:
        return (FileNotFoundError,)


async def _stat_or_none(afc, path):
    try:
        return await afc.stat(path)
    except _not_found_types():
        return None


@asynccontextmanager
async def lockdown_session():
    try:
        from pymobiledevice3 import usbmux
        from pymobiledevice3.lockdown import create_using_usbmux
    except Exception as error:
        raise connection_failure(error, 'modules') from error
    try:
        devices = [d for d in await usbmux.list_devices() if d.is_usb]
    except Exception as error:
        raise connection_failure(error, 'usb') from error
    if len(devices) != 1:
        raise AppFilesError(
            'Conecta un solo iPhone por USB para acceder a los archivos de sus apps.'
            if not devices else 'Se detectó más de un dispositivo Apple. Conecta un solo iPhone para continuar.',
            'app-files:usb-device-count',
        )
    try:
        lockdown = await create_using_usbmux(serial=devices[0].serial, connection_type='USB', autopair=False, label='TUPAQ')
    except Exception as error:
        raise connection_failure(error, 'lockdown') from error
    async with lockdown:
        if not (lockdown.paired and lockdown.session_id):
            raise AppFilesError('No se pudo validar la autorización existente del ordenador.', 'app-files:trust-missing')
        yield lockdown


@asynccontextmanager
async def app_documents(bundle_id):
    valid = validate_bundle_id(bundle_id)
    try:
        from pymobiledevice3.services.house_arrest import HouseArrestService
        from pymobiledevice3.exceptions import AppNotInstalledError
    except Exception as error:
        raise connection_failure(error, 'modules') from error
    async with lockdown_session() as lockdown:
        try:
            service = await HouseArrestService.create(lockdown, valid, documents_only=True)
        except AppNotInstalledError as error:
            raise AppFilesError('La aplicación seleccionada ya no está instalada en el iPhone.', 'app-files:not-installed') from error
        except Exception as error:
            raise AppFilesError(
                'iOS no permitió abrir la carpeta Documentos de esta aplicación. Solo las apps con intercambio de archivos habilitado permiten acceso por USB.',
                f'app-files:house-arrest:{type(error).__name__}',
            ) from error
        async with service as afc:
            yield afc


async def list_sharing_apps(proxy):
    """Return user apps that explicitly enable UIFileSharingEnabled."""
    apps = await proxy.get_apps(application_type='User')
    if not isinstance(apps, dict):
        return []
    result = []
    for key, info in apps.items():
        if not isinstance(info, dict):
            continue
        if info.get('UIFileSharingEnabled') not in (True, 1):
            continue
        bundle_id = info.get('CFBundleIdentifier') or key
        try:
            bundle_id = validate_bundle_id(bundle_id)
        except AppFilesError:
            continue
        name = info.get('CFBundleDisplayName') or info.get('CFBundleName') or bundle_id
        version = info.get('CFBundleShortVersionString') or info.get('CFBundleVersion') or ''
        result.append({
            'bundle_id': bundle_id,
            'name': str(name),
            'version': str(version) if version is not None else '',
        })
    result.sort(key=lambda item: (text_key(item['name']), item['bundle_id'].casefold()))
    return result


async def list_folder(afc, relative=''):
    """List files and subfolders inside /Documents[/relative]."""
    clean = normalize_relative(relative)
    target = documents_path(clean)
    names = await afc.listdir(target)
    if len(names) > MAX_ENTRIES:
        raise AppFilesError('La carpeta supera el límite de 10.000 elementos visibles.', 'app-files:too-many-entries')
    entries = []
    for name in names:
        checkpoint()
        if not isinstance(name, str) or name in ('.', '..') or name.startswith(TEMP_PREFIX):
            continue
        try:
            validate_name(name)
        except AppFilesError:
            continue
        rel = _child_relative(clean, name)
        info = await _stat_or_none(afc, f'{target}/{name}')
        if not isinstance(info, dict):
            continue
        kind_flag = info.get('st_ifmt')
        kind = 'dir' if kind_flag == 'S_IFDIR' else 'link' if kind_flag == 'S_IFLNK' else 'file'
        size = info.get('st_size') if kind == 'file' and type(info.get('st_size')) is int and info.get('st_size') >= 0 else None
        modified = info.get('st_mtime') if isinstance(info.get('st_mtime'), datetime) else None
        entries.append({'name': name, 'relative': rel, 'kind': kind, 'size': size, 'modified': modified})
    entries.sort(key=lambda item: (0 if item['kind'] == 'dir' else 1, text_key(item['name'])))
    return entries


async def create_folder(afc, relative, folder_name):
    """Create a new folder inside /Documents[/relative] without overwriting anything."""
    name = validate_name(folder_name.strip() if isinstance(folder_name, str) else '')
    rel = _child_relative(relative, name)
    target = documents_path(rel)
    if await _stat_or_none(afc, target) is not None:
        raise AppFilesError('Ya existe un archivo o carpeta con ese nombre.', 'app-files:exists')
    await afc.makedirs(target)
    created = await _stat_or_none(afc, target)
    if not isinstance(created, dict) or created.get('st_ifmt') != 'S_IFDIR':
        raise AppFilesError('No se pudo verificar la creación de la carpeta en el iPhone.', 'app-files:mkdir-verify')
    return rel


def _collect_local_uploads(local_paths):
    """Collect local files and empty subfolders without following directory symlinks."""
    files = []
    folders = []
    seen_folders = set()
    visited_dirs = 0
    for raw in local_paths:
        checkpoint()
        source = Path(raw)
        if not source.exists():
            raise AppFilesError('Uno de los archivos seleccionados ya no existe.', 'app-files:source-missing')
        name = validate_name(source.name)
        if source.is_file():
            size = source.stat().st_size
            if size > MAX_FILE_BYTES:
                raise AppFilesError('Un archivo supera el límite de 4 GB.', 'app-files:file-size')
            files.append((source, name, size))
        elif source.is_dir() and not source.is_symlink():
            pending = [(source, name)]
            while pending:
                checkpoint()
                current, rel = pending.pop(0)
                visited_dirs += 1
                if visited_dirs > MAX_FOLDERS:
                    raise AppFilesError('La selección supera el límite de 500 carpetas.', 'app-files:too-many-folders')
                if rel not in seen_folders:
                    seen_folders.add(rel)
                    folders.append(rel)
                with os.scandir(current) as it:
                    children = sorted(it, key=lambda entry: entry.name.casefold())
                for entry in children:
                    checkpoint()
                    if entry.is_symlink():
                        continue
                    child_name = validate_name(entry.name)
                    child_rel = f'{rel}/{child_name}'
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((Path(entry.path), child_rel))
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        if size > MAX_FILE_BYTES:
                            raise AppFilesError('Un archivo supera el límite de 4 GB.', 'app-files:file-size')
                        files.append((Path(entry.path), child_rel, size))
                        if len(files) > MAX_UPLOAD_FILES:
                            raise AppFilesError('La selección supera el límite de 2.000 archivos por envío.', 'app-files:too-many-files')
        else:
            raise AppFilesError('Solo se pueden copiar archivos y carpetas normales.', 'app-files:source-type')
        if len(files) > MAX_UPLOAD_FILES:
            raise AppFilesError('La selección supera el límite de 2.000 archivos por envío.', 'app-files:too-many-files')
    return folders, files


async def _verify_remote_file(afc, remote_path, expected_size, expected_digest):
    info = await _stat_or_none(afc, remote_path)
    if not isinstance(info, dict) or info.get('st_ifmt') != 'S_IFREG' or info.get('st_size') != expected_size:
        raise AppFilesError('El archivo copiado no coincide con el tamaño esperado.', 'app-files:upload-size')
    digest = hashlib.sha256()
    handle = await afc.fopen(remote_path, 'r')
    remaining = expected_size
    try:
        while remaining > 0:
            checkpoint()
            block = await afc.fread(handle, min(CHUNK, remaining))
            if not block or len(block) > remaining:
                raise AppFilesError('La verificación del archivo copiado quedó incompleta.', 'app-files:upload-truncated')
            digest.update(block)
            remaining -= len(block)
    finally:
        await afc.fclose(handle)
    if digest.hexdigest() != expected_digest:
        raise AppFilesError('La comprobación de integridad del archivo copiado falló.', 'app-files:upload-hash')


async def upload_paths(afc, relative, local_paths, progress=None):
    """Upload local files/folders into /Documents[/relative] with SHA-256 verification."""
    clean = normalize_relative(relative)
    parent = documents_path(clean)
    parent_stat = await _stat_or_none(afc, parent)
    if not isinstance(parent_stat, dict) or parent_stat.get('st_ifmt') != 'S_IFDIR':
        raise AppFilesError('La carpeta de destino ya no existe en la aplicación.', 'app-files:dest-missing')
    folders, files = _collect_local_uploads(local_paths)
    if not folders and not files:
        return {'uploaded': 0, 'skipped': 0, 'folders_created': 0, 'cancelled': False}
    folders_created = 0
    for folder_rel in folders:
        checkpoint()
        remote_dir = documents_path(f'{clean}/{folder_rel}' if clean else folder_rel)
        existing = await _stat_or_none(afc, remote_dir)
        if existing is None:
            await afc.makedirs(remote_dir)
            folders_created += 1
        elif existing.get('st_ifmt') != 'S_IFDIR':
            raise AppFilesError('Ya existe un archivo con el mismo nombre que una carpeta a subir.', 'app-files:dir-collision')

    total_bytes = sum(max(1, size) for _, _, size in files) or 1
    done_bytes = 0
    uploaded = 0
    skipped = 0
    for index, (source, rel_sub, size) in enumerate(files):
        try:
            checkpoint()
        except TransferCancelled:
            return {'uploaded': uploaded, 'skipped': skipped, 'folders_created': folders_created, 'cancelled': True}
        remote_rel = f'{clean}/{rel_sub}' if clean else rel_sub
        remote = documents_path(remote_rel)
        if await _stat_or_none(afc, remote) is not None:
            skipped += 1
            done_bytes += max(1, size)
            if progress:
                progress(min(100, round(done_bytes * 100 / total_bytes)), 100, f'Omitido (ya existe): {source.name}')
            continue
        remote_parent = str(PurePosixPath(remote).parent)
        tmp = f'{remote_parent}/{TEMP_PREFIX}{uuid.uuid4().hex}'
        local_hash = hashlib.sha256()
        if progress:
            progress(min(99, round(done_bytes * 100 / total_bytes)), 100, f'Copiando {index + 1} de {len(files)}: {source.name}')
        try:
            handle = await afc.fopen(tmp, 'w')
            try:
                with source.open('rb') as stream:
                    while True:
                        checkpoint()
                        block = stream.read(CHUNK)
                        if not block:
                            break
                        await afc.fwrite(handle, block)
                        local_hash.update(block)
                        done_bytes += len(block)
                        if progress:
                            progress(min(99, round(done_bytes * 100 / total_bytes)), 100, f'Copiando {index + 1} de {len(files)}: {source.name}')
            finally:
                await afc.fclose(handle)
            if size == 0:
                done_bytes += 1
            await _verify_remote_file(afc, tmp, size, local_hash.hexdigest())
            if await _stat_or_none(afc, remote) is not None:
                with suppress(Exception):
                    await afc.rm_single(tmp, force=True)
                skipped += 1
                continue
            await afc.rename(tmp, remote)
            uploaded += 1
        except TransferCancelled:
            with suppress(Exception):
                await afc.rm_single(tmp, force=True)
            return {'uploaded': uploaded, 'skipped': skipped, 'folders_created': folders_created, 'cancelled': True}
        except Exception:
            with suppress(Exception):
                await afc.rm_single(tmp, force=True)
            raise
    if progress:
        progress(100, 100, 'Copia completada.')
    return {'uploaded': uploaded, 'skipped': skipped, 'folders_created': folders_created, 'cancelled': False}


async def _collect_remote_exports(afc, relative_paths):
    """Expand selected remote files/folders without following symlinks."""
    files = []
    folders = []
    visited_dirs = 0
    for raw in relative_paths:
        checkpoint()
        rel = normalize_relative(raw)
        if not rel:
            raise AppFilesError('Selecciona un archivo o carpeta concreto para exportar.', 'app-files:export-root')
        remote = documents_path(rel)
        info = await _stat_or_none(afc, remote)
        if not isinstance(info, dict):
            raise AppFilesError('Uno de los elementos seleccionados ya no existe en el iPhone.', 'app-files:export-missing')
        kind = info.get('st_ifmt')
        top_name = rel.rsplit('/', 1)[-1]
        if kind == 'S_IFREG':
            size = info.get('st_size')
            if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
                raise AppFilesError('El archivo supera el tamaño admitido para exportar.', 'app-files:file-size')
            files.append((remote, Path(top_name), size))
        elif kind == 'S_IFDIR':
            pending = [(remote, Path(top_name))]
            while pending:
                checkpoint()
                cur_remote, cur_local = pending.pop(0)
                visited_dirs += 1
                if visited_dirs > MAX_FOLDERS:
                    raise AppFilesError('La exportación supera el límite de 500 carpetas.', 'app-files:too-many-folders')
                folders.append(cur_local)
                for name in await afc.listdir(cur_remote):
                    checkpoint()
                    if not isinstance(name, str) or name in ('.', '..') or name.startswith(TEMP_PREFIX):
                        continue
                    validate_name(name)
                    child_remote = f'{cur_remote}/{name}'
                    child_info = await _stat_or_none(afc, child_remote)
                    if not isinstance(child_info, dict):
                        continue
                    child_kind = child_info.get('st_ifmt')
                    if child_kind == 'S_IFDIR':
                        pending.append((child_remote, cur_local / name))
                    elif child_kind == 'S_IFREG':
                        size = child_info.get('st_size')
                        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
                            raise AppFilesError('Un archivo supera el tamaño admitido para exportar.', 'app-files:file-size')
                        files.append((child_remote, cur_local / name, size))
                        if len(files) > MAX_UPLOAD_FILES:
                            raise AppFilesError('La exportación supera el límite de 2.000 archivos.', 'app-files:too-many-files')
        # Symlinks are skipped safely rather than followed.
    return folders, files


async def export_entries(afc, relative_paths, destination_folder, progress=None):
    """Export selected remote files/folders to destination_folder without overwriting existing files."""
    destination = Path(destination_folder).resolve()
    if not destination.is_dir():
        raise AppFilesError('La carpeta de destino en el ordenador no existe.', 'app-files:local-dest')
    folders, files = await _collect_remote_exports(afc, relative_paths)
    for folder_rel in folders:
        target_dir = (destination / folder_rel).resolve()
        if destination not in target_dir.parents:
            raise AppFilesError('Ruta local de destino no válida.', 'app-files:local-path')
        target_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = sum(max(1, size) for _, _, size in files) or 1
    done_bytes = 0
    exported = 0
    skipped = 0
    with tempfile.TemporaryDirectory(prefix='.tupaq-app-export-', dir=destination) as temp_dir:
        temp_root = Path(temp_dir)
        for index, (remote, local_rel, size) in enumerate(files):
            try:
                checkpoint()
            except TransferCancelled:
                return {'exported': exported, 'skipped': skipped, 'cancelled': True}
            target = (destination / local_rel).resolve()
            if destination not in target.parents:
                raise AppFilesError('Ruta local de destino no válida.', 'app-files:local-path')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                skipped += 1
                done_bytes += max(1, size)
                if progress:
                    progress(min(100, round(done_bytes * 100 / total_bytes)), 100, f'Omitido (ya existe): {local_rel.name}')
                continue
            staged = temp_root / f'item-{index}'
            if progress:
                progress(min(99, round(done_bytes * 100 / total_bytes)), 100, f'Exportando {index + 1} de {len(files)}: {local_rel.name}')
            handle = await afc.fopen(remote, 'r')
            remaining = size
            try:
                with staged.open('wb') as output:
                    while remaining > 0:
                        checkpoint()
                        block = await afc.fread(handle, min(CHUNK, remaining))
                        if not block or len(block) > remaining:
                            raise AppFilesError('La lectura del archivo desde el iPhone quedó incompleta.', 'app-files:export-truncated')
                        output.write(block)
                        remaining -= len(block)
                        done_bytes += len(block)
                        if progress:
                            progress(min(99, round(done_bytes * 100 / total_bytes)), 100, f'Exportando {index + 1} de {len(files)}: {local_rel.name}')
            except TransferCancelled:
                return {'exported': exported, 'skipped': skipped, 'cancelled': True}
            finally:
                await afc.fclose(handle)
            if size == 0:
                done_bytes += 1
            if staged.stat().st_size != size:
                raise AppFilesError('El archivo exportado no coincide con el tamaño original.', 'app-files:export-size')
            if target.exists():
                skipped += 1
                continue
            shutil.move(str(staged), str(target))
            exported += 1
    if progress:
        progress(100, 100, 'Exportación completada.')
    return {'exported': exported, 'skipped': skipped, 'cancelled': False}


async def delete_entries(afc, relative_paths, progress=None):
    """Delete selected files or folders strictly inside /Documents."""
    targets = []
    for raw in relative_paths:
        rel = normalize_relative(raw)
        if not rel:
            raise AppFilesError('No se puede eliminar la carpeta raíz Documentos.', 'app-files:delete-root')
        targets.append((rel, documents_path(rel)))
    if not targets:
        return {'deleted': 0, 'cancelled': False}
    deleted = 0
    for index, (rel, remote) in enumerate(targets):
        try:
            checkpoint()
        except TransferCancelled:
            return {'deleted': deleted, 'cancelled': True}
        name = rel.rsplit('/', 1)[-1]
        if progress:
            progress(round(index * 100 / len(targets)), 100, f'Eliminando {index + 1} de {len(targets)}: {name}')
        info = await _stat_or_none(afc, remote)
        if info is None:
            continue
        if info.get('st_ifmt') == 'S_IFDIR':
            await afc.rm(remote)
        else:
            await afc.rm_single(remote)
        if await _stat_or_none(afc, remote) is not None:
            raise AppFilesError('No se pudo confirmar la eliminación del elemento en el iPhone.', 'app-files:delete-verify')
        deleted += 1
    if progress:
        progress(100, 100, 'Eliminación completada.')
    return {'deleted': deleted, 'cancelled': False}


async def _run_action_async(action, bundle_id=None, relative='', payload=None, progress=None):
    if action == 'list_apps':
        from pymobiledevice3.services.installation_proxy import InstallationProxyService
        async with lockdown_session() as lockdown:
            async with InstallationProxyService(lockdown) as proxy:
                return {'action': 'list_apps', 'apps': await list_sharing_apps(proxy)}
    async with app_documents(bundle_id) as afc:
        if action == 'list_folder':
            entries = await list_folder(afc, relative)
            return {'action': 'list_folder', 'bundle_id': bundle_id, 'relative': normalize_relative(relative), 'entries': entries}
        if action == 'create_folder':
            created = await create_folder(afc, relative, payload)
            entries = await list_folder(afc, relative)
            return {'action': 'create_folder', 'bundle_id': bundle_id, 'relative': normalize_relative(relative), 'created': created, 'entries': entries}
        if action == 'upload':
            summary = await upload_paths(afc, relative, payload or [], progress=progress)
            entries = None if summary.get('cancelled') else await list_folder(afc, relative)
            return {'action': 'upload', 'bundle_id': bundle_id, 'relative': normalize_relative(relative), 'entries': entries, **summary}
        if action == 'export':
            items, destination = payload
            summary = await export_entries(afc, items, destination, progress=progress)
            return {'action': 'export', 'bundle_id': bundle_id, 'relative': normalize_relative(relative), **summary}
        if action == 'delete':
            summary = await delete_entries(afc, payload or [], progress=progress)
            entries = None if summary.get('cancelled') else await list_folder(afc, relative)
            return {'action': 'delete', 'bundle_id': bundle_id, 'relative': normalize_relative(relative), 'entries': entries, **summary}
    raise AppFilesError('Acción de archivos de aplicación no reconocida.', 'app-files:action')


def run_app_action(action, bundle_id=None, relative='', payload=None, progress=None):
    token = CURRENT.set(getattr(progress, 'control', None))
    try:
        return asyncio.run(_run_action_async(action, bundle_id, relative, payload, progress))
    except AppFilesError:
        raise
    except LibraryError as error:
        raise AppFilesError(str(error), error.diagnostic) from error
    except TransferCancelled:
        return {'action': action, 'cancelled': True}
    except Exception as error:
        raise AppFilesError(
            'No se pudo completar la operación en los archivos de la aplicación.',
            f'app-files:{action}:{type(error).__name__}',
        ) from error
    finally:
        CURRENT.reset(token)
