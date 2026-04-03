# Guía de copy y alertas operator-friendly v1

## 1. Propósito

Definir cómo debe hablar la GUI local de CKv2 y cómo deben comportarse sus alertas visibles para operario y técnico.

## 2. Contrato de alertas

## 2.1 Formato

Las alertas principales futuras de la app local deben ser toasts apilados.

Ubicación congelada:

- esquina inferior izquierda.

Cada toast debe incluir:

- título corto;
- mensaje de una línea o dos como máximo;
- severidad visible;
- y acción opcional solo si aporta.

## 2.2 Tipos

### Éxito

Uso:

- operación iniciada;
- operación detenida;
- acción completada;
- firmware importado;
- configuración aplicada.

Duración sugerida:

- 4 s.

### Informativo

Uso:

- cambio de vista;
- selección aplicada;
- servicio remoto habilitado;
- operación pendiente.

Duración sugerida:

- 5 s.

### Advertencia

Uso:

- operación parcial;
- caja con degradación;
- falta una condición no crítica;
- hay algo que revisar pronto.

Duración sugerida:

- 7-8 s o hasta siguiente interacción.

### Error

Uso:

- no se pudo iniciar operación;
- caja caída;
- acción remota fallida;
- error de conexión o control-plane.

Duración sugerida:

- persistente hasta dismiss o hasta quedar reemplazada por un estado de recuperación.

## 2.3 Lo que un toast no debe mostrar

No mostrar como mensaje principal:

- nombres de variables;
- rutas internas;
- `cmd_seq`;
- `nonce`;
- excepciones Python crudas;
- códigos de error internos sin traducción;
- textos largos tipo log.

## 3. Política de lenguaje por superficie

## 3.1 Mapa / Home

Tono:

- corto;
- directo;
- operativo;
- sin jerga innecesaria.

Ejemplos:

- `Operación activa`
- `Caja 3 con advertencia`
- `2 nodos sin conexión`
- `Control listo`

## 3.2 Operación

Tono:

- operativo con apoyo técnico ligero.

Ejemplos:

- `La operación está lista para iniciar`
- `Falta preparar la sesión`
- `No se pudo iniciar la operación por configuración incompleta`

## 3.3 Nodos en vivo

Tono:

- operacional-técnico.

Sí permite:

- RSSI
- última nota
- pérdida
- uptime

pero con etiquetas claras.

## 3.4 Estado técnico

Tono:

- técnico explícito;
- orientado a soporte/diagnóstico.

Aquí sí caben:

- nombres de backend;
- control-plane;
- resolución;
- errores detallados;
- métricas internas.

## 3.5 Control F3

Tono:

- técnico de acción controlada.

Debe ser claro, pero no necesita esconder vocabulario de protocolo.

## 3.6 Firmware

Tono:

- técnico productizado.

Debe explicar con claridad:

- artifact;
- versión;
- estado;
- current;
- deploy;
- campaign.

## 4. Tabla de traducción UX

### Usar en vez de

- `Iniciar sesión` en home principal
  - usar `Iniciar operación`
- `Detener sesión`
  - usar `Detener operación`
- `Error de backend`
  - usar `No se pudo activar el canal de operación`
- `profile.active inválido`
  - usar `Falta completar la configuración del perfil`
- `node_unresolved`
  - usar `No se pudo ubicar el nodo en la red actual`

### Mantener solo en superficies técnicas

- `SessionState`
- `BackendKind`
- `cmd_seq`
- `nonce`
- `resolution_status`
- `ACK`
- `retry`

## 5. Redacción recomendada

### Correcto

- `Caja 2 con advertencia`
- `No se detectan nodos activos`
- `La operación sigue activa, pero una caja requiere revisión`
- `No se pudo aplicar el comando`

### Incorrecto

- `NodeRegistry empty`
- `ControlPlane unresolved`
- `profile.active null`
- `remote_api bind failed`

## 6. Acciones y botones

Los botones de primera capa deben usar verbos operativos:

- `Iniciar operación`
- `Detener operación`
- `Ver nodos`
- `Abrir firmware`
- `Revisar alerta`

Los botones técnicos pueden usar lenguaje específico:

- `PING`
- `REQUEST_STAT_NOW`
- `REBOOT_SOFT`
- `OTA Deploy`

## 7. Política de severidad visual

El sistema visual debe mapear:

- éxito -> verde;
- informativo -> teal;
- advertencia -> ámbar;
- error -> rojo.

No usar:

- dorado corporativo como error;
- rojo para calibración;
- demasiados colores distintos en una misma capa.

## 8. Decisión final congelada

La GUI local de CKv2 hablará en dos registros claros:

- registro operator-first en home, mapa y operación;
- registro técnico en `Nodos en vivo`, `Técnico`, `Control F3` y `Firmware`.

La home no debe volver a hablar como log o variable interna.
