# Design System CKv2

## Principios base
- Claridad operativa primero: la interfaz debe priorizar lectura y acción sin ruido.
- Consistencia transversal: Home, Nodos, Diagnóstico, Técnico y diálogos usan el mismo lenguaje.
- Semántica estable: estados, acciones y bloques mantienen identidad visual entre superficies.

## Tokens visuales principales
- Fondo app: `#F7F4EC`
- Superficie primaria: `#FFFEFC`
- Superficie secundaria: `#FFFDFC`
- Borde base: `#DCCFB8`
- Borde sutil: `#E1D5C2`
- Texto principal: `#0B3B27`
- Texto secundario: `#5B6F66`
- Acción primaria: `#2FAC66`
- Acción de peligro: `#C45245`

## Roles de botones
- `primary`: acción principal de la sección (confirmar/aplicar/abrir flujo principal).
- `secondary`: acción complementaria relevante.
- `contextual`: atajo operativo dentro del contexto actual.
- `ghost`: acción discreta de baja jerarquía.
- `danger`: acciones destructivas o de riesgo operativo.

## Semántica de estados (nodos)
- `online`: verde (`#2FAC66`)
- `calibrating`: azul (`#2F7ED8`)
- `degraded`: ámbar (`#DD8A12`)
- `offline`: rojo (`#C45245`)

Aplicación:
- Mapa: overlays, badges y halos.
- Nodos: color del estado en tabla.
- Chips/badges: soporte mediante `statusTone` para etiquetas Qt.

## Patrones de secciones y superficies
- `QGroupBox` es el contenedor base de secciones.
- `sectionRole` define variantes:
  - `summary`: lectura ejecutiva.
  - `actions`: acciones operativas.
  - `technical`: detalle técnico.
- `sectionTitleLabel` y `sectionHintLabel` unifican títulos/subtítulos de superficies.
- `nodesContextBar` usa patrón de barra contextual con borde y fondo suave.

## Diálogos y toasts
- Todos los diálogos usan fondo/espaciado del sistema global (`theme.qss`).
- Toasts usan `level` (`info/success/warning/error`) y mantienen paleta consistente con el resto de CKv2.

## Mantenimiento
- Evitar `setStyleSheet(...)` local para estilos globales.
- Preferir `role`, `sectionRole`, `statusTone` y object names definidos en `theme.qss`.
- Reutilizar `design_system.py` para semántica de estado y colores compartidos en widgets custom.
