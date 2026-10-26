# Botxito Anti-Raid (Python)

## Archivos
- `bot.py`: bot anti-raid con detección de entradas masivas y spam, aislamiento, registros, comandos y estados con emojis. También intenta conectarse al canal de voz configurado y reconectarse si pierde la conexión.
- `requirements.txt`: dependencias fijadas para voz, incluida `davey` (protocolo DAVE), PyNaCl y python-dotenv.
- `.env.example`: ejemplo de configuración; no contiene ningún token real.

## Configuración en FadeHost
1. Sube estos archivos a tu repositorio de GitHub.
2. Selecciona runtime **Python**.
3. Comando de inicio: `python bot.py`
4. En la configuración de instalación/build de FadeHost, asegúrate de que ejecute `pip install -r requirements.txt`. Si el hosting permite reinstalar dependencias o limpiar caché, hazlo después de actualizar el repositorio.
5. En los registros de inicio debe aparecer `[VOZ] Biblioteca davey cargada correctamente`. Si aparece `[VOZ] ERROR`, la instalación no está instalando `davey` y hay que revisar los logs del paso de instalación.
6. Añade en las variables de entorno de FadeHost: `DISCORD_TOKEN` con el token real del bot. No publiques el token en GitHub.
7. Añade `VOICE_CHANNEL_ID=1401644022144958595` si quieres configurar explícitamente el canal de voz. El código ya usa este ID como valor predeterminado.

## Intents de Discord
En Discord Developer Portal > aplicación > Bot, activa **Server Members Intent** y **Message Content Intent**, y guarda los cambios.

## Permisos del bot
En el servidor debe tener permiso para ver y conectar al canal de voz, además de los permisos de moderación que necesita el sistema anti-raid. El rol del bot debe estar por encima del rol `Aislado`.

## Canales y rol esperados
- Rol: `Aislado`
- Canal de registros: `anti-raid-logs`
- Canal de registros de aislamiento: `aislamientos`

Puedes cambiar estos nombres mediante variables de entorno si tu servidor usa otros nombres.

## Seguridad
Nunca añadas tu token a `bot.py`, `.env.example`, README ni a un repositorio público. Guarda el token como variable secreta en FadeHost. Si el token se expone, restablécelo desde Discord Developer Portal.
