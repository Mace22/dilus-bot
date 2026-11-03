# 📦 Cofres de Dilu's Bot

Sistema de **cofres diarios gratis** y **cofres comprables**. Solo entregan monedas (la misma economía de siempre).

## Cómo funciona la racha

- Un cofre gratis cada **24 horas** (reloj corrido en UTC: no depende del día del calendario ni de la zona horaria).
- Se puede reclamar **justo a las 24 h exactas**. Si reclamás antes, te dice cuánto falta.
- Si reclamás entre las 24 h y las 48 h (sin llegar a 48 h) del último cofre, la **racha sube**. A partir de las **48 h** se pierde y vuelve al día 1.
- La racha tiene su propio tiempo y su propio contador: **no usa ni modifica el `/daily`**, y abrir cofres comprados no toca la racha.
- Todo se calcula y guarda en el servidor (SQLite). El navegador nunca decide nada.

| Día de racha | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 en adelante |
|---|---|---|---|---|---|---|---|---|
| Cofre | Común | Común | Raro | Raro | Épico | Épico | Legendario | Legendario |

## Probabilidades y recompensas (solo monedas)

### 📦 Común  ·  precio 100  ·  promedio 81 (81% del precio)

| Tramo | Probabilidad | Monedas |
|---|---|---|
| Básico | 48,0% | 30 – 65 |
| Bueno | 28,0% | 65 – 100 |
| Muy bueno | 15,0% | 100 – 140 |
| Excelente | 7,0% | 140 – 210 |
| ¡Jackpot! | 2,0% | 210 – 320 |

### 🔷 Raro  ·  precio 200  ·  promedio 167 (83% del precio)

| Tramo | Probabilidad | Monedas |
|---|---|---|
| Básico | 46,0% | 80 – 130 |
| Bueno | 28,0% | 130 – 185 |
| Muy bueno | 15,0% | 185 – 260 |
| Excelente | 8,0% | 260 – 380 |
| ¡Jackpot! | 3,0% | 380 – 640 |

### 🔮 Épico  ·  precio 400  ·  promedio 314 (78% del precio)

| Tramo | Probabilidad | Monedas |
|---|---|---|
| Básico | 45,0% | 150 – 240 |
| Bueno | 28,0% | 240 – 340 |
| Muy bueno | 15,0% | 340 – 480 |
| Excelente | 9,0% | 480 – 700 |
| ¡Jackpot! | 3,0% | 700 – 1.300 |

### 👑 Legendario  ·  precio 600  ·  promedio 472 (79% del precio)

| Tramo | Probabilidad | Monedas |
|---|---|---|
| Básico | 44,0% | 250 – 380 |
| Bueno | 28,0% | 380 – 500 |
| Muy bueno | 15,0% | 500 – 650 |
| Excelente | 9,0% | 650 – 900 |
| ¡Jackpot! | 4,0% | 900 – 1.800 |

## Precios (comprables)

| Cofre | Precio | Premio promedio | Devuelve | Rango |
|---|---|---|---|---|
| 📦 Común | 100 | 81 | 81% | 30 – 320 |
| 🔷 Raro | 200 | 167 | 83% | 80 – 640 |
| 🔮 Épico | 400 | 314 | 78% | 150 – 1.300 |
| 👑 Legendario | 600 | 472 | 79% | 250 – 1.800 |

Comprar cofres **siempre resta monedas en promedio** (devuelven ~78-83% de lo que cuestan): es un sumidero, no una forma de generar monedas.

## Análisis de la economía (por qué estos valores)

Fuentes actuales de monedas, leídas del código del bot:

| Fuente | Valor |
|---|---|
| `/daily` | 200 + 25 por día de racha (tope 450) cada 24 h |
| `/trabajar` | 50 a 150 (promedio 100) cada hora |
| Chat | 1 a 3 monedas por minuto con actividad |
| Casino | resta a la larga (ruleta 2,7%, slots ~95% de retorno) |

- Una semana completa de cofres diarios (día 1 a 7) da en promedio **1.595 monedas**, unas **228 por día**.
- Con la racha en el máximo (cofre legendario todos los días): **~472 por día**, parecido a un `/daily` con racha máxima (450).
- Para un servidor de ~40 personas, si las 40 mantuvieran la racha máxima se entregarían ~19.000 monedas/día; en la práctica participa una parte, y las compras de cofres y el casino quitan monedas.
- Si notás inflación, bajá la escala (`/cofreadmin escala 0.7`) o subí los precios. Con `/cofreadmin estadisticas` ves el **neto** que inyectan los cofres.

## Comandos

| Comando | Qué hace |
|---|---|
| `/cofre info` | Racha, próximo cofre gratis, tus cofres y precios (Discord no deja usar `/cofre` solo: es un grupo, por eso se llama `info`) |
| `/cofre abrir` | Reclama y abre el cofre diario |
| `/cofre inventario` | Tus cofres comprados |
| `/cofre comprar` | Comprar 1 a 10 cofres de un tipo |
| `/cofre abrir_comprado` | Abrir uno del inventario |
| `/cofre ranking` | Mejores rachas |
| `/cofre probabilidades` | Tabla de premios y probabilidades |
| `/cofreadmin estadisticas` | Cofres abiertos y monedas entregadas (admins) |
| `/cofreadmin precio` | Cambia el precio de un cofre (admins) |
| `/cofreadmin escala` | Multiplica todas las recompensas, 0.25 a 4 (admins) |
| `/cofreadmin reiniciar_racha` | Reinicia la racha de alguien, con opción de dejarlo reclamar ya (admins) |

## Dónde se configura todo

- **`utils/chest_config.py`**: tiempos (24 h / 48 h), progresión de rachas, precios por defecto, tramos y probabilidades, colores y nombres.
- **`/cofreadmin`**: precios y escala de recompensas por servidor (se guardan en la tabla `chest_settings`).

## Seguridad y estabilidad

- **Abrir un cofre es UNA sola sentencia SQL** (tabla `chest_opens`) con triggers: valida el estado, consume la racha o el cofre del inventario, guarda el historial y acredita las monedas en el libro de la economía (`economy_ledger`). Si algo falla no se aplica nada.
- **Comprar es UNA sola sentencia** (tabla `chest_purchases`): cobra y suma al inventario, o no hace nada.
- **Idempotencia:** cada apertura/compra lleva un identificador único (`open_id` / `id`). Reintentar con el mismo identificador devuelve el mismo resultado y nunca cobra ni paga dos veces. El identificador incluye el servidor y la persona.
- **Doble clic y pedidos simultáneos:** un candado por persona + las comprobaciones de la base garantizan una sola apertura por cofre/día.
- **El premio se sortea en el servidor ANTES de la animación** y ya está acreditado cuando empieza. Si cerrás la página o recargás, el premio igual quedó acreditado una sola vez.
- Las monedas se mueven con el libro idempotente de la economía; los cofres nunca modifican `economy.balance` directamente ni crean otra economía.
- Migraciones: solo `CREATE TABLE/TRIGGER IF NOT EXISTS`. No se toca ni se recrea ninguna tabla existente ni `data/dilu.db`.
