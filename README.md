# ✨ Dilu's Bot

Bot de Discord en Python (discord.py 2.7) pensado para servidores chicos.

## Funciones

| Módulo | Comandos |
|---|---|
| 📈 **Niveles** (XP por mensajes **y por tiempo en voz**) | `/rank` (tarjeta con imagen), `/top` (nivel o horas en voz), `/horas`, `/xp dar`, `/xp reset`, `/levelrole agregar\|quitar\|lista` |
| 🎙️ **Voz 24/7** | `/entrar` (entra a tu canal, **silenciado y ensordecido**, y se reconecta solo si lo sacan o se cae), `/salir` |
| 🎁 **Sorteos** con botón | `/sorteo crear`, `/sorteo terminar` |
| 🎫 **Tickets** de soporte | `/ticket panel` |
| 👋 **Bienvenida / despedida / autorole** | `/config bienvenida\|despedida\|levelup\|autorole\|ver` |
| 🛡️ **Moderación** | `/clear`, `/kick`, `/ban`, `/timeout`, `/untimeout` |
| 🔧 **Utilidades** | `/ayuda`, `/ping`, `/avatar`, `/serverinfo`, `/encuesta` |

## 1. Crear el bot en Discord

1. Entrá a https://discord.com/developers/applications → **New Application** → ponele **Dilu's Bot**.
2. Pestaña **Bot** → poné el nombre y la foto que quieras → **Reset Token** y copiá el token.
3. En esa misma pestaña activá los **3 Privileged Gateway Intents**:
   - Presence Intent (opcional)
   - **Server Members Intent**
   - **Message Content Intent**
4. Pestaña **OAuth2 → URL Generator**: marcá `bot` y `applications.commands`.
   Permisos recomendados: *Manage Roles, Manage Channels, Kick Members, Ban Members, Moderate Members,
   Manage Messages, Send Messages, Embed Links, Attach Files, Add Reactions, Read Message History, Connect, Speak/View Channel*.
   (O simplemente **Administrator** si es tu servidor personal.)
5. Abrí la URL generada e invitá el bot a tu servidor.

> ⚠️ El rol del bot tiene que estar **por encima** de los roles que quieras que asigne (autorole, recompensas por nivel).

## 2. Subirlo a GitHub

```bash
cd dilus-bot
git init
git add .
git commit -m "Dilu's Bot"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/dilus-bot.git
git push -u origin main
```

El `.gitignore` ya evita que se suba el `.env` (token) y la base de datos.
**Nunca subas tu token a GitHub.** Si se filtra, reseteá el token en el portal de Discord.

## 3. Correrlo en FedeHost (o cualquier hosting de bots)

1. Cargá el repo (o subí los archivos) en el panel del hosting.
2. **Archivo de inicio:** `main.py`
3. **Requisitos:** `requirements.txt` (si el panel tiene un campo para eso; si no, ejecutá `pip install -r requirements.txt`).
4. **Token:** creá una variable de entorno `DISCORD_TOKEN` en el panel, o subí a mano un archivo `.env`
   (copiá `.env.example`, renombralo a `.env` y pegá el token).
5. Iniciá el servidor. En la consola tendría que aparecer `Conectado como Dilu's Bot...`.

Los comandos `/` pueden tardar unos minutos en aparecer la primera vez.

## Correrlo en tu PC (para probar)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env        # Linux/Mac: cp .env.example .env   → y pegá el token
python main.py
```

## Cómo usar la voz 24/7

1. Conectate a un canal de voz.
2. Ejecutá `/entrar` → el bot entra a ese canal, **muteado y ensordecido**.
3. Se queda ahí: si se cae la conexión, lo mueven o lo desconectan, **vuelve solo** (revisa cada 30 s, y a los 3 s si lo sacan).
4. Si reinicia el bot, vuelve al mismo canal automáticamente.
5. `/salir` para que se vaya y deje de reconectar.

Por defecto `/entrar` y `/salir` requieren el permiso **Gestionar canales**.

## Personalización rápida

- **XP, cooldown y mínimo de personas para XP de voz:** arriba de `cogs/levels.py`.
- **Color y nombre de los embeds:** `utils/embeds.py`.
- **Nombre/estado del bot:** nombre en el portal de Discord; estado ("Viendo Dilu's Bot | /ayuda") en `main.py`.

## Estructura

```
main.py            ← arranque
cogs/              ← cada módulo (levels, voice247, config, moderation, tickets, giveaways, utility)
utils/             ← base de datos (SQLite) y embeds
data/              ← acá se guarda dilu.db (no la borres si querés conservar los niveles)
```
