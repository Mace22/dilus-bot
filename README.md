# ✨ Dilu's Bot

Bot de Discord en Python (discord.py 2.7) pensado para servidores chicos.

## Funciones

| Módulo | Comandos |
|---|---|
| 📈 **Niveles** (XP por mensajes **y por tiempo en voz**) | `/rank` (tarjeta con imagen), `/top` (nivel u horas en voz), `/horas`, `/xp dar\|reset`, `/levelrole agregar\|quitar\|lista` |
| 🤖 **IA con Gemini** | `/ask`, `/olvidar`, `/traducir` y también charlás **mencionando al bot** (`@Dilu's Bot hola`). Recuerda la charla de cada persona |
| 💘 **Match** | `/match usuario1 [usuario2]` → imagen con los dos avatares, corazón que se llena y % de compatibilidad (siempre da lo mismo para la misma pareja) |
| 🪙 **Economía** | `/balance`, `/daily` (con racha), `/trabajar`, `/pay`, `/ricos`, `/apostar`, `/slots`, `/tienda`, `/comprar`. Se ganan monedas también chateando |
| 🎙️ **Voz 24/7** | `/entrar` (entra a tu canal **silenciado y ensordecido** y se queda siempre; si algo lo saca, vuelve solo), `/salir` |
| 🔊 **Canales de voz temporales** | Entrás a un canal "lobby" y se crea uno propio que se borra solo al quedar vacío (`/config tempvoice`) |
| 🛡️ **Moderación** | `/clear`, `/kick`, `/ban`, `/timeout`, `/untimeout`, `/warn`, `/warns`, `/unwarn`, `/clearwarns` (timeout automático a las 3 advertencias) |
| 📜 **Logs** | Mensajes borrados/editados, entradas/salidas, bans, timeouts y cambios de roles en un canal (`/config logs`) |
| 🎁 **Comunidad** | `/sorteo crear\|terminar`, `/ticket panel`, `/encuesta` |
| 👋 **Bienvenida** | `/config bienvenida\|despedida\|levelup\|autorole\|ver` |
| 🔧 **Utilidades** | `/ayuda`, `/ping`, `/avatar`, `/serverinfo` |

## 1. Crear el bot en Discord

1. Entrá a https://discord.com/developers/applications → **New Application** → ponele **Dilu's Bot**.
2. Pestaña **Bot** → poné el nombre y la foto que quieras → **Reset Token** y copiá el token.
3. En esa misma pestaña activá los Privileged Gateway Intents: **Server Members Intent** y **Message Content Intent**.
4. Pestaña **OAuth2 → URL Generator**: marcá `bot` y `applications.commands` y los permisos
   (o **Administrator** si es tu servidor personal). Abrí la URL e invitá el bot.

> ⚠️ El rol del bot tiene que estar **por encima** de los roles que quiera asignar (autorole, recompensas por nivel, tienda).

## 2. Conseguir la API key de Gemini (para la IA)

1. Entrá a https://aistudio.google.com/apikey con tu cuenta de Google.
2. **Create API key** y copiala.
3. Cargala como variable `GEMINI_API_KEY` en el hosting (o en el `.env`).

El modelo por defecto es `gemini-3.8-flash`. Si Google lo cambia o lo retira, no hace falta tocar código:
poné otro nombre en la variable `GEMINI_MODEL` (podés ver los vigentes en https://ai.google.dev/gemini-api/docs/models).
Si no cargás la key, el resto del bot funciona normal y `/ask` avisa que falta configurarla.

## 3. Subirlo a GitHub

```bash
git init
git add .
git commit -m "Dilu's Bot"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/dilus-bot.git
git push -u origin main
```

El `.gitignore` evita que se suban el `.env` (tokens) y la base de datos. **Nunca subas tus tokens/keys a GitHub.**

## 4. Correrlo en el hosting

1. Cargá el repo (o los archivos) en el panel.
2. **Archivo de inicio:** `main.py` — **Requisitos:** `requirements.txt`.
3. Variables de entorno: `DISCORD_TOKEN` y `GEMINI_API_KEY` (o subí un `.env`).
4. Iniciá el servidor. Tiene que aparecer `Conectado como Dilu's Bot...` y `IA lista (modelo: ...)`.

## Voz 24/7: cómo funciona

1. Conectate a un canal de voz y ejecutá `/entrar`: el bot entra, **silenciado y ensordecido**, y queda guardado.
2. **Modo presencia (por defecto):** el bot figura dentro del canal usando solo su conexión principal con Discord,
   sin abrir el enlace de audio. Ese enlace es el que se corta con errores como `Disconnected from voice`
   o `Could not connect to voice`, así que al no usarlo esos cortes ya no lo afectan.
3. Un vigilante revisa cada 20 segundos. Si el bot quedó afuera (lo desconectaron o se cayó la sesión), vuelve solo;
   nunca insiste más de una vez cada 30 s. Si reiniciás el bot, también vuelve al canal guardado.
4. `/salir` lo saca y desactiva el regreso automático hasta el próximo `/entrar`.

Si el modo presencia no te funciona, podés volver a la conexión de voz completa cargando la variable
`VOICE_MODE=real` en el hosting (por defecto es `presence`).

## Configuración rápida de extras

- **Logs:** `/config logs #canal`
- **Canales temporales:** creá un canal de voz "➕ Crear canal" y ejecutá `/config tempvoice` eligiéndolo.
  El bot necesita los permisos *Gestionar canales* y *Mover miembros*.
- **Tienda de roles:** `/economia tienda_agregar rol precio` → los usuarios compran con `/comprar`.
- **Tickets:** `/ticket panel` en el canal donde quieras el botón.

## Personalización

- **XP, cooldown y mínimo de personas para XP de voz:** arriba de `cogs/levels.py`.
- **Monedas (recompensas, apuestas, cooldowns):** arriba de `cogs/economy.py`.
- **Límite de warns y duración del timeout automático:** arriba de `cogs/warns.py`.
- **Color y nombre de los embeds:** `utils/embeds.py`.
- **Personalidad de la IA:** variable `GEMINI_SYSTEM_PROMPT`.

## Estructura

```
main.py            ← arranque
cogs/              ← módulos (levels, ai, match, economy, voice247, tempvoice, warns, config, moderation, tickets, giveaways, utility)
utils/             ← base de datos (SQLite), embeds y fuentes
assets/fonts/      ← fuente para las imágenes (soporta tildes y ñ)
data/              ← acá se guarda dilu.db (no la borres si querés conservar niveles y monedas)
```
