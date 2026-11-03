@echo off
setlocal
title Importios - Comprobar iPhone
echo.
echo IMPORTIOS - Primera comprobacion para Windows 11
echo.
echo Conecta el iPhone por USB, desbloquealo y acepta Confiar si aparece.
echo Este programa solo consulta Windows. No modifica el telefono.
echo No necesita permisos de administrador.
echo.
pause
powershell.exe -NoLogo -NoProfile -Command "& { $ErrorActionPreference = 'Stop'; Write-Output ''; Write-Output '=== Resultado de Importios ==='; try { $os = Get-CimInstance Win32_OperatingSystem; Write-Output ('Sistema: ' + $os.Caption + ' / compilacion ' + $os.BuildNumber) } catch { Write-Output 'Sistema: no se pudo consultar' }; try { $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object { $_.InstanceId -match '^USB\\VID_05AC&' }); if ($devices.Count -eq 0) { Write-Output 'USB Apple: no detectado. Prueba otro cable de datos o puerto USB.' } else { Write-Output ('Dispositivos USB Apple detectados: ' + $devices.Count); $phones = @($devices | Where-Object { $_.FriendlyName -match 'iPhone' }); Write-Output ('Entradas identificadas como iPhone: ' + $phones.Count); Write-Output ('Entradas USB Apple con estado OK: ' + @($devices | Where-Object { $_.Status -eq 'OK' }).Count); Write-Output 'Detectar un dispositivo Apple no confirma la conexion con Musica ni la autorizacion de confianza.' } } catch { Write-Output 'USB: no se pudo consultar. Comunica este resultado para revisarlo.' }; try { $services = @(Get-Service -ErrorAction Stop | Where-Object { $_.Name -match 'Apple Mobile Device' -or $_.DisplayName -match 'Apple Mobile Device' }); if ($services.Count -eq 0) { Write-Output 'Servicio Apple Mobile Device: no encontrado' } else { foreach ($service in $services) { Write-Output ('Servicio Apple Mobile Device: ' + $service.Status) } } } catch { Write-Output 'Servicio Apple: no se pudo consultar' }; try { $apps = @(Get-AppxPackage -ErrorAction Stop | Where-Object { $_.Name -match 'AppleInc\.(AppleDevices|iTunes)' }); if ($apps.Count -eq 0) { Write-Output 'Dispositivos Apple / iTunes de Microsoft Store: no detectados para este usuario' } else { foreach ($app in $apps) { Write-Output ('Aplicacion: ' + $app.Name + ' / version ' + $app.Version) } }; Write-Output 'La instalacion clasica de iTunes no se comprueba en esta prueba.' } catch { Write-Output 'Aplicaciones Apple: no se pudieron consultar' }; Write-Output ''; Write-Output 'Esta prueba no verifica la version de iOS ni importa canciones.'; Write-Output 'Puedes compartir una foto de este resultado. No incluye numeros de serie ni identificadores USB.' }"
if errorlevel 1 echo No se pudo completar la comprobacion con PowerShell.
echo.
echo La ventana permanecera abierta para que puedas leer el resultado.
pause
endlocal
