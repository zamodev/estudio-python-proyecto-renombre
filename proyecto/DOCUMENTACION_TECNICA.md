# File MVP — Manual Técnico

## Tabla de contenidos

1. [¿Qué hace este proyecto?](#1-qué-hace-este-proyecto)
2. [Requisitos previos](#2-requisitos-previos)
3. [Instalación y arranque](#3-instalación-y-arranque)
4. [Estructura del proyecto](#4-estructura-del-proyecto)
5. [Cómo funciona: el pipeline](#5-cómo-funciona-el-pipeline)
6. [Módulos y clases principales](#6-módulos-y-clases-principales)
7. [Configuración: archivos JSON](#7-configuración-archivos-json)
8. [Cómo agregar una nueva ruta vigilada](#8-cómo-agregar-una-nueva-ruta-vigilada)
9. [Cómo agregar un nuevo perfil de reglas](#9-cómo-agregar-un-nuevo-perfil-de-reglas)
10. [Tipos documentales: referencia rápida](#10-tipos-documentales-referencia-rápida)
11. [Modos de ejecución](#11-modos-de-ejecución)
12. [Preguntas frecuentes](#12-preguntas-frecuentes)

---

## 1. ¿Qué hace este proyecto?

**File MVP** es un servicio Python que vigila una o más carpetas del sistema de archivos y renombra automáticamente los documentos que llegan a ellas, ajustándolos a un formato canónico definido por negocio.

El formato canónico es:

```
TIPO_RUB_CEDULA.ext
```

Ejemplos:
| Nombre original | Nombre final |
|---|---|
| `EMB_RL01922670_1116280248 PARTE 1.zip` | `ASEMB_RL01922670_1116280248.zip` |
| `DES_RL01972021_1095802628 - Copy.zip` | `ASDES_RL01972021_1095802628.zip` |
| `SOL_RL01349425 CSV PARTE II_79350147.zip` | `SOL_RL01349425_79350147.zip` |
| `CR_DES_RL02172978_1214738554_FIDUCIARIA.pdf` | `CRDES_RL02172978_1214738554.pdf` |

Si el archivo ya cumple el formato, se mueve sin cambios. Si puede corregirse automáticamente, se mueve con el nombre corregido. Si no puede interpretarse, se rechaza (no se mueve).

---

## 2. Requisitos previos

| Componente | Versión mínima | Notas |
|---|---|---|
| Python | 3.9.x | El código es compatible con 3.9+. Probado en 3.12 y 3.14. |
| pip | cualquiera | Para instalar dependencias |
| watchdog | 4.0.1 | Única dependencia externa |

Verificar la versión de Python disponible:

```powershell
py --version        # Windows (lanzador py)
python --version    # Linux / macOS
```

---

## 3. Instalación y arranque

### 3.1 Clonar e instalar dependencias

```powershell
# Entrar al directorio del proyecto
cd proyecto

# (Recomendado) Crear entorno virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS

# Instalar dependencias
pip install -r requirements.txt
```

### 3.2 Configurar las rutas

Editar `config/watchers/documentos_principales.json` y ajustar:

```json
{
  "watch_path": "C:/ruta/a/la/carpeta-de-entrada",
  "destination_path": "C:/ruta/a/la/carpeta-de-salida"
}
```

> Las rutas pueden ser absolutas o relativas. En Windows usar `/` o `\\`.

### 3.3 Arrancar el servicio

```powershell
# Modo normal (vigila carpetas indefinidamente)
py -m app.main

# Con configuración alternativa
py -m app.main --config config/config.json

# Modo simulación: muestra qué haría sin mover archivos
py -m app.main --dry-run

# Con nivel de log detallado
py -m app.main --log-level DEBUG
```

### 3.4 Procesar archivos sueltos manualmente (sin watcher)

```python
# Desde la shell de Python dentro del directorio proyecto/
from app.config_loader import load_config
from app.processor import FileProcessor

config = load_config("config/config.json")
profile = config.rule_profiles["documentos_legales"]

processor = FileProcessor(
    destination_path="C:/salida",
    strategies_config=[...],  # ver config/watchers/documentos_principales.json
    rule_profile=profile,
    dry_run=True,             # False para mover en realidad
)
processor.process("C:/entrada/ASEMB_RL01234567_12345678.zip")
```

---

## 4. Estructura del proyecto

```
proyecto/
├── config/                          ← Toda la configuración (JSON)
│   ├── config.json                  ← Punto de entrada de configuración
│   ├── watchers/
│   │   └── documentos_principales.json   ← Ruta de entrada + salida
│   └── profiles/
│       └── documentos_legales/      ← Perfil de reglas documentales
│           ├── profile.json         ← Patrones RUB, cédula, limpieza, auto-fix
│           ├── document_types.json  ← Tipos documentales y sus reglas
│           ├── aliases.json         ← Alias simples (AS_EMB → ASEMB)
│           ├── extension_aliases.json  ← Alias dependientes de extensión
│           ├── pattern_fixes.json   ← Correcciones estructurales por regex
│           └── zip_policy.json      ← Política de filtrado interno de ZIPs
│
├── app/                             ← Código fuente
│   ├── main.py                      ← Punto de entrada (CLI)
│   ├── config_loader.py             ← Carga y deserializa los JSON
│   ├── config_models.py             ← Dataclasses de configuración
│   ├── models.py                    ← FileContext + ProcessingStatus
│   ├── processor.py                 ← Ejecuta el pipeline sobre un archivo
│   ├── registry.py                  ← Mapeo nombre → clase de estrategia
│   ├── watcher.py                   ← Integración watchdog (FileHandler)
│   ├── watcher_manager.py           ← Gestiona múltiples watchers
│   ├── exceptions.py                ← Jerarquía de excepciones
│   ├── zip_content_filter.py        ← Filtra contenido interno de ZIPs
│   └── strategies/                  ← Una clase por paso del pipeline
│       ├── normalize_filename.py
│       ├── apply_pattern_fixes.py
│       ├── resolve_alias.py
│       ├── strip_parte.py
│       ├── parse_document_name.py
│       ├── build_canonical_name.py
│       └── validate_business_rules.py
│
├── requirements.txt
└── MANUAL_TECNICO.md
```

---

## 5. Cómo funciona: el pipeline

Cuando llega un archivo, pasa por **7 pasos en secuencia**. Cada paso puede modificar el nombre o rechazar el archivo. Si en cualquier paso el estado llega a `REJECTED`, los pasos siguientes no hacen nada.

```
Archivo detectado
       │
       ▼
┌─────────────────────────────┐
│ 1. NormalizeFilename        │  Limpia: mayúsculas, espacios→_, guiones→_,
│                             │  múltiples___→_, quita caracteres especiales,
│                             │  elimina prefijos ruido (COPY, COPIA...)
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 2. ApplyPatternFixes        │  Aplica correcciones regex del archivo
│                             │  pattern_fixes.json (ej. elimina _CSV_)
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 3. ResolveAlias             │  Sustituye alias documentales:
│                             │  alias_map (AS_EMB→ASEMB) +
│                             │  extension_alias_map (EMB+.zip→ASEMB)
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 4. StripParte               │  Solo ZIPs: detecta y elimina referencias
│                             │  PARTE (ej. _PARTE_1, _VI_PARTE, _CSV_PARTE)
│                             │  Rescata la cédula si estaba después del corte
│                             │  Elimina sufijos romanos pegados a la cédula
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 5. ParseDocumentName        │  Extrae tipo documental, RUB y cédula
│                             │  a partir de los tokens del nombre
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 6. BuildCanonicalName       │  Reconstruye el nombre en formato canónico
│                             │  TIPO_RUB_CEDULA.ext y sincroniza tokens
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ 7. ValidateBusinessRules    │  Verifica: tipo documental válido, RUB válido,
│                             │  cédula requerida presente, extensión permitida,
│                             │  número de segmentos correcto
└────────────┬────────────────┘
             │
        ┌────┴────┐
        │         │
      VALID    REJECTED
   AUTO_FIXED
        │
        ▼
  (ZIP) Filtrar contenido interno
  según zip_policy
        │
        ▼
  Mover archivo a carpeta destino
```

### Estados posibles al final

| Estado | Significado |
|---|---|
| `VALID` | El archivo ya tenía el nombre correcto |
| `AUTO_FIXED` | Se corrigió automáticamente y se movió |
| `REJECTED` | No pudo interpretarse; no se mueve, se registra el error |

---

## 6. Módulos y clases principales

### `FileContext` (models.py)

Es el objeto que viaja por todo el pipeline. Cada estrategia lo recibe, lo puede modificar y lo devuelve.

```python
@dataclass
class FileContext:
    source_path: Path          # Ruta original del archivo en disco
    filename: str              # Nombre actual (se actualiza en cada paso)
    stem: str                  # Nombre sin extensión
    suffix: str                # Extensión en minúsculas (.zip, .pdf)
    original_filename: str     # Nombre con el que llegó (nunca cambia)
    tokens: list[str]          # Segmentos del nombre separados por _
    document_type: str         # Ej: "ASEMB", "SOL"
    rub: str                   # Ej: "RL01922670"
    cedula: str                # Ej: "1116280248"
    status: ProcessingStatus   # PENDING → VALID / AUTO_FIXED / REJECTED
    fixes_applied: list[str]   # Log de correcciones aplicadas
    validation_errors: list[str]  # Errores si fue rechazado
    is_parte: bool             # True si se detectó y eliminó una referencia PARTE
```

### `FileProcessor` (processor.py)

Orquesta el pipeline. Recibe la ruta del archivo, crea un `FileContext`, ejecuta todas las estrategias en orden, aplica el filtro ZIP si corresponde y mueve el archivo al destino.

### `RuleProfile` (config_models.py)

Representa un perfil de reglas. Contiene todos los parámetros que las estrategias necesitan: tipos documentales, patrones de RUB, cédula, alias, reglas de limpieza, política ZIP, etc.

### `WatchProfile` (config_models.py)

Representa una carpeta vigilada: ruta de entrada, ruta de salida, perfil de reglas asociado y parámetros de estabilidad del archivo.

### `FileHandler` / `DirectoryWatcher` (watcher.py)

Integración con la librería `watchdog`. `FileHandler` reacciona a eventos del sistema de archivos (`on_created`, `on_moved`) y espera a que el archivo se estabilice en tamaño antes de procesarlo.

### `WatcherManager` (watcher_manager.py)

Inicia y detiene todos los `DirectoryWatcher` activos. Es el objeto que mantiene vivo el proceso con `run_forever()`.

### `ZipContentFilter` (zip_content_filter.py)

Extrae el ZIP, filtra sus entradas internas y lo reempaqueta con estructura plana (sin subcarpetas). Opera en dos modos:
- **`parte`**: conserva solo las extensiones en `parte_keep_extensions` (ej. `.xls`, `.csv`)
- **`general`**: elimina las extensiones en `general_remove_extensions` (ej. `.mp4`, `.msg`)

---

## 7. Configuración: archivos JSON

### 7.1 `config/config.json` — Punto de entrada

```json
{
  "log_level": "INFO",
  "watchers": [
    "watchers/documentos_principales.json"
  ],
  "rule_profiles": [
    "profiles/documentos_legales"
  ]
}
```

| Campo | Descripción |
|---|---|
| `log_level` | Nivel de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `watchers` | Lista de rutas relativas a archivos JSON de watcher (dentro de `config/`) |
| `rule_profiles` | Lista de rutas relativas a **directorios** de perfil (dentro de `config/`) |

---

### 7.2 `config/watchers/<nombre>.json` — Carpeta vigilada

```json
{
  "name": "documentos_principales",
  "watch_path": "C:/ruta/de/entrada",
  "destination_path": "C:/ruta/de/salida",
  "rules_profile": "documentos_legales",
  "process_existing_on_startup": true,
  "recursive": false,
  "stable_wait_seconds": 1,
  "stability_checks": 3
}
```

| Campo | Descripción |
|---|---|
| `name` | Identificador del watcher (solo para logs) |
| `watch_path` | Carpeta que se vigila |
| `destination_path` | Carpeta donde se mueven los archivos procesados |
| `rules_profile` | Nombre del perfil de reglas que se aplica |
| `process_existing_on_startup` | Si `true`, procesa archivos ya presentes al arrancar |
| `recursive` | Si `true`, vigila subcarpetas también |
| `stable_wait_seconds` | Segundos entre chequeos de estabilidad de tamaño |
| `stability_checks` | Cantidad de chequeos consecutivos iguales antes de considerar estable |

---

### 7.3 `config/profiles/<nombre>/profile.json` — Reglas base del perfil

```json
{
  "rub_patterns": ["^RL\\d{8}$", "^RQL\\d{12}$"],
  "cedula_pattern": "^\\d{6,12}$",
  "cleanup_rules": {
    "uppercase": true,
    "replace_spaces_with_underscore": true,
    "replace_hyphen_with_underscore": true,
    "collapse_multiple_underscores": true,
    "remove_special_characters": true,
    "remove_prefixes": ["COPIA", "COPY"]
  },
  "auto_fix_policy": {
    "allow_pattern_fixes": true,
    "allow_alias_fix": true,
    "allow_separator_fix": true,
    "allow_case_fix": true,
    "allow_special_character_fix": true,
    "allow_extension_normalization": false,
    "allow_rub_guessing": false,
    "allow_cedula_guessing": false
  }
}
```

| Campo | Descripción |
|---|---|
| `rub_patterns` | Expresiones regulares que definen un RUB válido |
| `cedula_pattern` | Expresión regular para una cédula válida |
| `cleanup_rules` | Transformaciones mecánicas sobre el nombre crudo |
| `remove_prefixes` | Palabras que se eliminan si aparecen al inicio del stem |
| `auto_fix_policy` | Qué tipos de correcciones automáticas están permitidas |

---

### 7.4 `document_types.json` — Tipos documentales

```json
{
  "ASEMB": {
    "requires_cedula": true,
    "default_extension": ".zip",
    "allowed_extensions": [".zip", ".pdf"]
  },
  "CR": {
    "requires_cedula": false,
    "default_extension": ".pdf",
    "allowed_extensions": [".pdf"]
  }
}
```

| Campo | Descripción |
|---|---|
| `requires_cedula` | Si `true`, el archivo debe tener cédula en el nombre |
| `default_extension` | Extensión esperada por defecto |
| `allowed_extensions` | Lista de extensiones válidas para este tipo |

---

### 7.5 `aliases.json` — Alias simples

Mapeo directo de un prefijo incorrecto al tipo documental correcto, sin importar la extensión del archivo.

```json
{
  "AS_EMB": "ASEMB",
  "CR_EMB": "CREMB",
  "AS_DES": "ASDES",
  "CR_DES": "CRDES"
}
```

---

### 7.6 `extension_aliases.json` — Alias dependientes de extensión

Cuando el alias correcto depende de si el archivo es `.zip` o `.pdf`:

```json
{
  "EMB": { ".zip": "ASEMB", ".pdf": "CREMB" },
  "DES": { ".zip": "ASDES", ".pdf": "CRDES" }
}
```

Se evalúa como fallback si el prefijo no está en `aliases.json`.

---

### 7.7 `pattern_fixes.json` — Correcciones por regex

Reglas que transforman el stem completo con un `fullmatch` y un reemplazo tipo `re.sub`.

```json
[
  {
    "name": "strip_csv_infix",
    "match": "^(.+)_CSV_(.+)$",
    "replace": "\\1_\\2",
    "description": "Elimina el infijo _CSV_ entre el RUB y la cédula",
    "enabled": true
  }
]
```

| Campo | Descripción |
|---|---|
| `name` | Identificador de la regla (solo para logs) |
| `match` | Regex aplicada con `fullmatch` al stem normalizado |
| `replace` | Patrón de reemplazo (grupos con `\\1`, `\\2`, ...) |
| `description` | Texto que aparece en el log cuando se aplica |
| `enabled` | Si `false`, la regla se ignora |

---

### 7.8 `zip_policy.json` — Filtrado de contenido ZIP

```json
{
  "parte_detection_patterns": [
    "PARTE[_]?\\d+",
    "PARTE[_]?[IVX]+",
    "[IVX]+[_]?PARTE",
    "CSV[_]?PARTE",
    "^PARTE$"
  ],
  "strip_roman_suffix_from_token": true,
  "parte_keep_extensions": [".xls", ".xlsx", ".xlsm", ".csv"],
  "general_remove_extensions": [".mp4", ".avi", ".mov", ".msg", ".eml"]
}
```

| Campo | Descripción |
|---|---|
| `parte_detection_patterns` | Regex para detectar tokens PARTE en el nombre |
| `strip_roman_suffix_from_token` | Si `true`, quita sufijos romanos pegados a la cédula (`095784782II` → `095784782`) |
| `parte_keep_extensions` | En modo PARTE: conservar solo estos tipos de archivo dentro del ZIP |
| `general_remove_extensions` | En modo general: eliminar estos tipos de archivo del ZIP |

---

## 8. Cómo agregar una nueva ruta vigilada

Supón que quieres vigilar `C:/entrada-contratos` y depositar los resultados en `C:/salida-contratos`.

**Paso 1** — Crear el archivo de watcher:

```json
// config/watchers/contratos.json
{
  "name": "contratos",
  "watch_path": "C:/entrada-contratos",
  "destination_path": "C:/salida-contratos",
  "rules_profile": "documentos_legales",
  "process_existing_on_startup": true,
  "recursive": false,
  "stable_wait_seconds": 1,
  "stability_checks": 3
}
```

**Paso 2** — Registrarlo en `config/config.json`:

```json
{
  "log_level": "INFO",
  "watchers": [
    "watchers/documentos_principales.json",
    "watchers/contratos.json"
  ],
  "rule_profiles": [
    "profiles/documentos_legales"
  ]
}
```

**Paso 3** — Reiniciar el servicio. No se necesita cambiar ningún código Python.

---

## 9. Cómo agregar un nuevo perfil de reglas

Útil cuando una segunda área de negocio tiene tipos documentales distintos.

**Paso 1** — Crear la carpeta del perfil:

```
config/profiles/contratos_especiales/
    profile.json
    document_types.json
    aliases.json            (opcional)
    extension_aliases.json  (opcional)
    pattern_fixes.json      (opcional)
    zip_policy.json         (opcional)
```

**Paso 2** — Definir los tipos documentales en `document_types.json`:

```json
{
  "CONT": {
    "requires_cedula": true,
    "default_extension": ".pdf",
    "allowed_extensions": [".pdf", ".docx"]
  },
  "ANEXO": {
    "requires_cedula": false,
    "default_extension": ".pdf",
    "allowed_extensions": [".pdf"]
  }
}
```

**Paso 3** — Registrar el perfil en `config/config.json`:

```json
{
  "rule_profiles": [
    "profiles/documentos_legales",
    "profiles/contratos_especiales"
  ]
}
```

**Paso 4** — Crear o editar un watcher que apunte a este perfil:

```json
{
  "name": "contratos_especiales",
  "watch_path": "C:/entrada-contratos",
  "destination_path": "C:/salida-contratos",
  "rules_profile": "contratos_especiales"
}
```

---

## 10. Tipos documentales: referencia rápida

| Tipo | Descripción | Requiere cédula | Extensiones válidas |
|---|---|---|---|
| `CR` | Certificado de registro | No | `.pdf` |
| `ASEMB` | Asamblea de acreedores | Sí | `.zip`, `.pdf` |
| `CREMB` | Certificado de asamblea | Sí | `.zip`, `.pdf` |
| `ASDES` | Asamblea de desvinculación | Sí | `.zip` |
| `CRDES` | Certificado de desvinculación | Sí | `.pdf` |
| `SOL` | Solicitud | Sí | `.zip` |

### Alias reconocidos automáticamente

| Prefijo incorrecto | Extensión | Se convierte en |
|---|---|---|
| `AS_EMB` | cualquiera | `ASEMB` |
| `CR_EMB` | cualquiera | `CREMB` |
| `AS_DES` | cualquiera | `ASDES` |
| `CR_DES` | cualquiera | `CRDES` |
| `EMB` | `.zip` | `ASEMB` |
| `EMB` | `.pdf` | `CREMB` |
| `DES` | `.zip` | `ASDES` |
| `DES` | `.pdf` | `CRDES` |

---

## 11. Modos de ejecución

### Modo normal

```powershell
py -m app.main
```

Vigila las carpetas indefinidamente. Para detener: `Ctrl+C`.

### Modo dry-run (simulación)

```powershell
py -m app.main --dry-run
```

Muestra en el log exactamente qué haría (nombres corregidos, archivos rechazados) **sin mover ni modificar ningún archivo**. Ideal para validar la configuración antes de poner en producción.

### Nivel de log

```powershell
py -m app.main --log-level DEBUG    # Muestra cada paso del pipeline
py -m app.main --log-level WARNING  # Solo errores y advertencias
```

### Configuración alternativa

```powershell
py -m app.main --config otra/ruta/config.json
```

---

## 12. Preguntas frecuentes

**¿Qué pasa si un archivo llega mientras otro se está copiando?**
El watcher espera a que el tamaño del archivo sea estable durante N chequeos consecutivos (`stability_checks` × `stable_wait_seconds`) antes de procesarlo.

**¿Puede el mismo archivo ser procesado dos veces?**
No. `FileProcessor` mantiene un lock interno por ruta; si el mismo archivo llega de nuevo mientras se está procesando, el segundo evento se descarta.

**¿Qué pasa con los archivos rechazados?**
Se registra el motivo del rechazo en el log y el archivo **permanece en la carpeta de origen** sin ser movido ni modificado.

**¿Cómo sé qué correcciones se aplicaron?**
El log muestra, por cada archivo, la lista de correcciones (`fixes_applied`) y el estado final. Con `--log-level DEBUG` se ve el estado del contexto en cada paso del pipeline.

**¿Puedo tener múltiples perfiles activos al mismo tiempo?**
Sí. Cada watcher apunta a exactamente un perfil, pero pueden existir múltiples watchers activos apuntando a perfiles distintos.

**¿El orden de las `pattern_fixes` importa?**
Sí. Se aplican en el orden en que aparecen en el JSON y solo se aplica la primera que hace match. Las demás se ignoran para ese archivo.
