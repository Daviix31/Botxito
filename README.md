# Anti-Raid Discord Bot (Python)

Bot de moderación para Discord: detecta entradas masivas y spam, asigna el rol `Aislado`, activa alertas de emergencia, registra aislamientos en un canal separado y rota su presencia.

## Archivos
- `bot.py`: código del bot.
- `requirements.txt`: librerías que necesita.
- `README.md`: estas instrucciones.

## Antes de arrancar
1. Crea una aplicación en https://discord.com/developers/applications.
2. En la pestaña **Bot**, activa **Server Members Intent** y **Message Content Intent**.
3. Copia el token como secreto privado; nunca lo publiques en el repositorio.
4. En tu servidor crea:
   - un rol llamado `Aislado`;
   - un canal privado `anti-raid-logs` para alertas;
   - un canal privado `aislamientos` para registrar cada usuario aislado.
5. En ambos canales, da acceso solo al equipo de moderación y al bot.
6. Coloca el rol del bot por encima de `Aislado` y de los roles de miembros que debe moderar.
7. Invita el bot con el scope `bot` y permisos: Manage Roles, View Channels, Send Messages, Read Message History y Manage Messages.

## Variables de entorno
Configura estas variables en tu hosting (por ejemplo, en la sección Environment Variables):

| Variable | Valor predeterminado | Para qué sirve |
|---|---|---|
| `DISCORD_TOKEN` | (obligatorio) | Token secreto del bot |
| `QUARANTINE_ROLE_NAME` | `Aislado` | Nombre exacto del rol |
| `LOG_CHANNEL_NAME` | `anti-raid-logs` | Canal de alertas |
| `QUARANTINE_LOG_CHANNEL_NAME` | `aislamientos` | Canal separado de aislamientos |
| `JOIN_WINDOW_SECONDS` | `20` | Ventana para contar entradas |
| `JOIN_THRESHOLD` | `6` | Entradas necesarias para activar emergencia |
| `EMERGENCY_SECONDS` | `180` | Duración inicial de emergencia |
| `QUARANTINE_NEW_MEMBERS_DURING_RAID` | `true` | Aislar nuevas entradas durante emergencia |
| `SPAM_WINDOW_SECONDS` | `8` | Ventana anti-spam |
| `SPAM_MESSAGE_THRESHOLD` | `6` | Mensajes antes de detectar spam |
| `DUPLICATE_THRESHOLD` | `4` | Mensajes repetidos antes de actuar |
| `PRESENCE_ROTATION_SECONDS` | `45` | Reservado para ajustar la rotación (actualmente el ciclo es de 45 s) |

## Ejecutarlo localmente en Windows
Instala Python 3.10 o superior. Abre CMD en la carpeta del proyecto y ejecuta:

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
```

En CMD, define el token solo para esa sesión:

```bat
set DISCORD_TOKEN=PEGA_AQUI_EL_TOKEN
py bot.py
```

También puedes crear un archivo `.env` con `DISCORD_TOKEN=...`, pero **no lo subas a GitHub**. Añade `.env` a `.gitignore`.

## Subirlo a GitHub
1. Crea un repositorio nuevo.
2. Sube `bot.py`, `requirements.txt` y `README.md`.
3. No subas el token ni el archivo `.env`.
4. GitHub guarda el código, pero **no mantiene el bot ejecutándose por sí solo**. Para que esté 24/7 debes desplegarlo en un hosting compatible con procesos Python y añadir `DISCORD_TOKEN` como variable secreta. Verifica que el servicio permita procesos persistentes y revisa sus límites de uso.

## Presencia rotativa
Cada 45 segundos intenta alternar entre:
- En línea — `Jugando a proteger servidores`
- Ausente — `Viendo N usuarios aislados`
- No molestar — `Jugando a vigilar posibles raids`
- En línea — `Escuchando alertas de seguridad`

Discord controla cómo muestra la presencia. La rotación no significa que el bot deje de funcionar cuando aparece como ausente o no molestar.

## Comandos
- `!ayuda`
- `!estado` (administrador)
- `!emergencia` (administrador)
- `!finemergencia` (administrador)
- `!aislar @usuario motivo` (administrador)
- `!desaislar @usuario` (administrador)

## Comportamiento y límites
- Se activa una emergencia cuando entran al menos 6 miembros en 20 segundos.
- Durante una emergencia, las nuevas entradas pueden recibir `Aislado`.
- Spam detectado puede provocar aislamiento y alerta.
- El modo emergencia de este código genera alertas y aplica aislamiento a sospechosos; **no cambia automáticamente los permisos de todos los canales**. Configura permisos de canales o utiliza una función de bloqueo revisada si necesitas cerrar la escritura de todo el servidor.
- La detección puede producir falsos positivos. Ajusta umbrales según el tráfico habitual.
- Discord limita las acciones de bots. No pruebes el sistema organizando un raid real.
