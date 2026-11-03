# ✨ Dilu's Bot

Bot de Discord en Python (discord.py 2.7) pensado para servidores chicos.

## Funciones

| Módulo | Comandos |
|---|---|
| 📈 **Niveles** (XP por mensajes **y por tiempo en voz**) | `/rank` (tarjeta con imagen), `/top` (nivel u horas en voz), `/horas`, `/xp dar\|reset`, `/levelrole agregar\|quitar\|lista` |
| 🤖 **IA con Gemini** | `/ask`, `/olvidar`, `/traducir` y también charlás **mencionando al bot** (`@Dilu's Bot hola`). Recuerda la charla de cada persona |
| 💘 **Match** | `/match usuario1 [usuario2]` → imagen con los dos avatares, corazón que se llena y % de compatibilidad (siempre da lo mismo para la misma pareja) |
| 🃏 **Blackjack** | `/blackjack apuesta` → mesa con cartas en imagen que ve todo el chat. Botones **Pedir / Plantarse / Doblar**, el dealer se planta en 17, el Blackjack paga 3:2 y hay botón para jugar otra mano. Se juega con las monedas de la economía |
| 🎡 **Ruleta** | `/ruleta [tiempo]` → abre una mesa en el canal y **todo el chat** puede apostar con las monedas de la economía: Rojo/Negro, Par/Impar, 1-18/19-36, docenas, columnas y número pleno. Tablero en imagen con las fichas de cada zona, rueda animada, pagos al instante y guía didáctica (botón ❓). Si el bot se reinicia a mitad de una ronda, devuelve las apuestas |
| 📦 **Cofres** | `/cofre info\|abrir\|inventario\|comprar\|abrir_comprado\|ranking\|probabilidades` → cofre diario gratis con racha propia (común → legendario) y cofres comprables, con ruleta de apertura en Discord y en el panel web. Solo dan monedas. Admins: `/cofreadmin`. Detalles en `COFRES.md` |
| 🌐 **Panel web** | `/panel` → abre una página con tu saldo, `/daily` y `/trabajar` con cuenta regresiva, nivel/XP/horas en voz, **ruleta, blackjack y tragamonedas** jugables con animaciones y sonido, **logros**, historial con gráfico de ganancias, **envío de monedas**, tienda de roles y rankings. Entrás con tu cuenta de Discord |
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

Por defecto el bot prueba estos modelos **en orden** (todos tienen cupo gratis): `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.6-flash`.
Si uno está saturado, sin cupo o ya no existe, pasa solo al siguiente.
Podés elegir tus propios modelos con la variable `GEMINI_MODEL` (uno o varios separados por coma), por ejemplo
`gemini-3.5-flash-lite,gemini-3.1-flash-lite`. Los vigentes están en https://ai.google.dev/gemini-api/docs/models.
(Los modelos `2.5` ya no sirven: Google los apagó el 16 de octubre de 2026.)
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

## Panel web (opcional)

Una página integrada al bot, con el mismo saldo y las mismas reglas que en Discord:

- **Inicio:** saldo, `/daily` y `/trabajar` con cuenta regresiva, nivel/XP, mensajes, horas en voz, puestos y tus números del casino.
- **Juegos:** ruleta (tablero con fichas y rueda animada), blackjack (cartas 3D, mazo, fichas) y tragamonedas (carretes, palanca y tabla de pagos), todos con **sonido** (se sintetiza en el navegador, sin archivos) y efectos de confeti y monedas.
- **Logros:** 21 medallas (bronce, plata y oro), gráfico de tu evolución en el casino e historial de jugadas.
- **Enviar monedas** a otra persona (mismas reglas que `/pay`), tienda de roles y rankings.
- Botón de sonido en la barra superior (silencio y volumen, se recuerda por navegador).

Se activa sola cuando cargás las variables.

1. **Developer Portal** (discord.com/developers) → tu aplicación → **OAuth2**:
   - Copiá el **Client Secret** (si no lo ves, "Reset Secret") y cargalo en el hosting como `DISCORD_CLIENT_SECRET`.
   - En **Redirects** agregá `https://TU-DIRECCION/auth/callback` (tiene que ser idéntica a `WEB_BASE_URL` + `/auth/callback`).
2. Variables de entorno en el hosting:

   | Variable | Para qué |
   | --- | --- |
   | `DISCORD_CLIENT_SECRET` | Client Secret de la app (obligatoria; sin esto el panel queda apagado y el bot funciona igual) |
   | `WEB_BASE_URL` | Dirección pública del panel, ej. `https://panel.midominio.com` o `http://123.45.67.89:25565` |
   | `WEB_PORT` | Puerto donde escucha. Si no está, usa `SERVER_PORT` (Pterodactyl), `PORT` o `8080` |
   | `SESSION_SECRET` | (opcional) clave para firmar las sesiones; si falta se deriva del token del bot |

3. Reiniciá el bot. En el log tiene que aparecer `Panel web escuchando en ...` y `Redirect URI para el Developer Portal: ...`.
4. En Discord usá **`/panel`** y tocá el botón, o entrá directo a la dirección.

Notas:
- Tu hosting tiene que **exponer un puerto/URL público** hacia el bot (no todos los planes gratuitos lo permiten).
- Para HTTPS usá un dominio con proxy (Cloudflare, Nginx, Caddy) o un túnel (Cloudflare Tunnel).
- Las sesiones duran 3 días y se firman con HMAC; las acciones que mueven monedas se validan siempre en el servidor.
- Si el bot se reinicia con una mano de blackjack abierta, la apuesta se devuelve al volver.
- Las constantes (recompensas, apuestas mínimas y máximas, cooldowns) se toman de los mismos archivos que los comandos.

## Configuración rápida de extras

- **Logs:** `/config logs #canal`
- **Canales temporales:** creá un canal de voz "➕ Crear canal" y ejecutá `/config tempvoice` eligiéndolo.
  El bot necesita los permisos *Gestionar canales* y *Mover miembros*.
- **Tienda de roles:** `/economia tienda_agregar rol precio` → los usuarios compran con `/comprar`.
- **Tickets:** `/ticket panel` en el canal donde quieras el botón.

## Personalización

- **XP, cooldown y mínimo de personas para XP de voz:** arriba de `cogs/levels.py`.
- **Monedas (recompensas, apuestas, cooldowns):** arriba de `cogs/economy.py`.
- **Blackjack (apuesta mínima/máxima, mazos, velocidad del dealer):** arriba de `cogs/blackjack.py`.
- **Ruleta (apuesta mínima/máxima, tiempo de la mesa, apuestas por persona):** arriba de `cogs/roulette.py`.
- **Límite de warns y duración del timeout automático:** arriba de `cogs/warns.py`.
- **Color y nombre de los embeds:** `utils/embeds.py`.
- **Personalidad de la IA:** variable `GEMINI_SYSTEM_PROMPT`.

## Estructura

```
main.py            ← arranque
cogs/              ← módulos (levels, ai, match, economy, blackjack, roulette, voice247, tempvoice, warns, config, moderation, tickets, giveaways, utility)
utils/             ← base de datos (SQLite), embeds, fuentes y lógica de la ruleta
COFRES.md          ← guía del sistema de cofres (probabilidades, precios, configuración)
web/               ← panel web (servidor aiohttp, API y la página en web/static/)
assets/fonts/      ← fuente para las imágenes (soporta tildes y ñ)
data/              ← acá se guarda dilu.db (no la borres si querés conservar niveles y monedas)
```
