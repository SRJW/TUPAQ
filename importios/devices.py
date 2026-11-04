"""Read-only discovery through the local Apple USB multiplexing service.

Only ListDevices is sent: no pairing, device connection, file writes or sync.
Windows needs Apple's device service/driver, macOS uses its built-in usbmuxd.
"""
import plistlib
import hashlib
import secrets
import socket
import struct
import sys

SESSION_NONCE=secrets.token_bytes(32)

def device_token(serial):
    # In-memory binding only: changes every app launch, never written to journals.
    return hashlib.sha256(SESSION_NONCE+str(serial).encode('utf-8')).hexdigest()


HEADER = struct.Struct('<IIII')
MAX_REPLY = 1024 * 1024


class DiscoveryError(Exception):
    pass


def receive_exact(stream, size):
    parts = bytearray()
    while len(parts) < size:
        chunk = stream.recv(size-len(parts))
        if not chunk:
            raise DiscoveryError('El servicio de Apple cerró la conexión antes de responder.')
        parts.extend(chunk)
    return bytes(parts)


def read_devices(stream, fingerprint=False):
    request = plistlib.dumps({'MessageType': 'ListDevices', 'ProgName': 'TUPAQ',
                             'ClientVersionString': 'TUPAQ', 'kLibUSBMuxVersion': 3})
    stream.sendall(HEADER.pack(len(request)+HEADER.size, 1, 8, 1)+request)
    length, version, message, tag = HEADER.unpack(receive_exact(stream, HEADER.size))
    if not HEADER.size < length <= MAX_REPLY or (version, message, tag) != (1, 8, 1):
        raise DiscoveryError('El servicio de Apple devolvió una cabecera no válida.')
    try:
        reply = plistlib.loads(receive_exact(stream, length-HEADER.size))
    except (ValueError, plistlib.InvalidFileException, OverflowError) as error:
        raise DiscoveryError('No se pudo interpretar la respuesta del servicio de Apple.') from error
    if not isinstance(reply, dict) or not isinstance(reply.get('DeviceList'), list):
        raise DiscoveryError('El servicio de Apple no devolvió una lista de dispositivos.')
    devices = []
    for device in reply['DeviceList']:
        properties = device.get('Properties') if isinstance(device, dict) else None
        if not isinstance(properties, dict):
            raise DiscoveryError('La lista contiene información de dispositivo no válida.')
        if properties.get('ConnectionType') == 'USB':
            # Do not return serial numbers, pairing records, or identifiers.
            entry = {'connection':'USB'}
            if fingerprint:
                # Ephemeral comparison token only; never display/persist it.
                raw = str(device.get('DeviceID',''))+'\0'+str(properties.get('SerialNumber',''))
                entry['token'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            devices.append(entry)
    return devices


def discover(fingerprint=False):
    try:
        if sys.platform == 'win32':
            stream = socket.create_connection(('127.0.0.1', 27015), timeout=4)
        else:
            stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stream.settimeout(4)
            try:
                stream.connect('/var/run/usbmuxd')
            except OSError:
                stream.close()
                raise
        with stream:
            stream.settimeout(4)
            return read_devices(stream,fingerprint=fingerprint)
    except OSError as error:
        raise DiscoveryError('No se pudo consultar el servicio local de Apple. En Windows se necesita '
            'el controlador de Apple; en Mac comprueba la conexión USB. No se ha iniciado ninguna sincronización.') from error
