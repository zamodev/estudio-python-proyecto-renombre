# File MVP

Proyecto en Python para monitorear una o varias carpetas, validar nombres documentales, autocorregir errores conocidos y mover solo los archivos que cumplen el estándar configurado.

## Requisitos

- Python 3.9.12+
- watchdog

## Instalación

pip install -r requirements.txt

## Ejecución

Desde la carpeta `proyecto`:

- `py -m app.main`

## Configuración

Editar `config.json`.

La configuración ahora se divide en dos niveles:

- `watchers`: definen qué carpetas se monitorean y a qué ruta destino se mueven los archivos válidos.
- `rule_profiles`: definen reglas documentales reutilizables, patrones de RUB, reglas de limpieza, pattern fixes y aliases configurables.

Cada watcher puede apuntar a un perfil usando `rules_profile`, lo que evita duplicar reglas entre carpetas.

## Pipeline actual

- `NormalizeFilenameStrategy`
- `ApplyPatternFixesStrategy`
- `ResolveAliasStrategy`
- `ApplyNamingTemplateStrategy`
- `ParseDocumentNameStrategy`
- `BuildCanonicalNameStrategy`
- `ValidateBusinessRulesStrategy`

Este pipeline permite:

- normalizar separadores, mayúsculas y caracteres especiales
- corregir errores estructurales configurables como `EMBRQL... -> ASEMB_RQL...`
- corregir aliases documentales configurables como `AS_EMB -> ASEMB`
- aplicar plantillas de renombrado por casuística, por ejemplo `2_RTA_... -> 2RTA_...`
- validar tipos documentales, RUB, cédula y extensión
- reconstruir nombres canónicos antes de mover el archivo
- dejar en origen los archivos que no se pueden validar con seguridad

Las plantillas de naming viven en `config/profiles/<perfil>/naming_templates.json` y se activan de forma automática cuando el perfil las define.

## Manejo de errores

El proyecto usa excepciones propias para separar problemas de configuración, estabilidad de archivos, construcción de estrategias y procesamiento de archivos. Además, el flujo registra eventos con `logging`, incluyendo:

- archivos corregidos y movidos
- archivos rechazados que permanecen en origen
- motivos de rechazo para facilitar auditoría y depuración
