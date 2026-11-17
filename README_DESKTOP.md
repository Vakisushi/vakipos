# Vaki Sushi POS para Windows

Esta es la nueva aplicación nativa. Utiliza la misma base de datos
`sushi_pos.db` que la versión web, pero no necesita FastAPI, Uvicorn ni un
navegador para funcionar.

La versión web se conserva temporalmente en `main.py` como respaldo durante la
migración.

## Instalar

Desde PowerShell, dentro del proyecto:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecutar

```powershell
.\venv\Scripts\python.exe .\desktop_main.py
```

La aplicación se abre maximizada e incluye:

- Inicio de sesión usando los usuarios existentes.
- Catálogo por categorías y búsqueda.
- Carrito con cantidades e indicaciones de cocina.
- Validación acumulada de ingredientes.
- Creación atómica de órdenes y descuento de inventario.
- Ticket de cliente y comanda de cocina.
- Impresión directa en la impresora `XP-58`.
- Consulta y edición de existencias y mínimos.
- Historial, detalle y cobro de pedidos.
- Alta y edición de productos con sus recetas.
- Alta de ingredientes.
- Reportes por método de pago.
- Cierre de caja basado solo en efectivo desde el cierre anterior.
- Usuarios nuevos con contraseña protegida mediante PBKDF2.
- Respaldos manuales y respaldo automático antes de migrar la base.

## Datos y seguridad

La base se encuentra en `sushi_pos.db`. La primera ejecución crea una copia
previa a la migración dentro de `backups`. También se puede crear un respaldo en
cualquier momento desde Administración.

Los usuarios históricos continúan funcionando con su contraseña anterior para
conservar compatibilidad. Los usuarios nuevos sí se guardan con contraseña
derivada mediante PBKDF2.

## Construir el ejecutable

Ejecuta `construir_exe.bat`. El programa terminado se crea en:

```text
dist\Vaki Sushi POS\Vaki Sushi POS.exe
```

La carpeta completa debe mantenerse junta porque contiene las librerías y la
base de datos. El constructor nunca reemplaza una base que ya exista dentro de
la carpeta de distribución.
# Pedidos móviles por QR

Al abrir `main.py`, el POS inicia también el servidor de pedidos móviles en el
puerto `8787`. Se crean diez mesas y sus imágenes QR dentro de
`codigos_qr_mesas`. Los códigos se regeneran en cada inicio usando la dirección
IP actual de la computadora.

Para probarlo desde un teléfono:

1. Conecta la computadora del POS y el teléfono a la misma red Wi-Fi.
2. Abre el POS y permite el acceso en el aviso de Firewall de Windows para
   redes privadas.
3. Escanea uno de los PNG de `codigos_qr_mesas`.
4. Agrega productos y envía el pedido. La comanda se imprime de inmediato y el
   pedido queda disponible en **Pedidos y cobros**.

Si el QR abre en la computadora pero no en el teléfono, solicita al proveedor
de la red desactivar **aislamiento de clientes/AP** y reservar una IP fija para
la computadora del POS. Si la IP cambia, abre nuevamente el POS y vuelve a
imprimir los códigos QR regenerados.
