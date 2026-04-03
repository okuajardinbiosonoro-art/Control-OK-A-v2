# Home Map State Contract

## 1. Proposito

Este documento congela la semantica visual y la politica de agregacion de estados para la futura Home guiada por mapa de CKv2.

Complementa el contrato principal definido en [desktop_shell_operator_first.md](desktop_shell_operator_first.md).

## 2. Estados operativos canonicos

La Home y el mapa usan exactamente estos estados operativos:

- `online`
- `calibrating`
- `degraded`
- `offline`

La fuente de verdad de estos estados es la semantica ya existente en runtime y `NodeRegistry`.

## 3. Significado operacional

### `online`

Uso:

- trafico reciente y saludable;
- sin degradacion activa;
- sin calibracion activa;
- nodo o caja disponible para operacion normal.

### `calibrating`

Uso:

- ventana de arranque o recuperacion reciente;
- evidencia de reboot reciente o periodo de estabilizacion;
- no debe presentarse como fallo mientras no exista degradacion real.

### `degraded`

Uso:

- trafico parcial;
- perdida elevada;
- nodos faltantes en una caja;
- mezcla de salud no critica pero no completa.

### `offline`

Uso:

- sin paquetes recientes;
- sin actividad util;
- perdida operativa total de un nodo o de una caja.

## 4. Prioridad relativa

La prioridad de severidad queda congelada asi:

1. `offline`
2. `degraded`
3. `calibrating`
4. `online`

La UI puede apoyarse en color, iconografia y copy breve, pero la prioridad operacional no depende del color final.

## 5. Politica de caja agregada

La caja agrega el estado de sus nodos esperados.

### Regla general

- si no existe snapshot util todavia, se muestra placeholder neutro no operativo;
- si todos los nodos esperados estan sin actividad util, la caja es `offline`;
- si hay actividad parcial, nodos faltantes o mezcla con degradacion, la caja es `degraded`;
- si no hay degradacion ni perdida total, pero existe calibracion activa, la caja es `calibrating`;
- solo cuando la caja esta completa y saludable, la caja es `online`.

### Razon de negocio

Esta politica evita dos errores comunes:

- pintar como `offline` una caja que aun conserva actividad parcial util;
- pintar como `online` una caja incompleta solo porque un nodo sigue vivo.

## 6. Regla de lectura en Home

La Home debe priorizar:

- lectura rapida de severidad;
- `conectados / esperados`;
- acceso a detalle contextual;
- orientacion espacial.

La Home no muestra por defecto:

- tablas completas;
- razones largas por nodo;
- trazas de diagnostico;
- variables de firmware o mantenimiento.

## 7. Integracion con runtime

La agregacion por caja debe construirse desde una capa de presentacion pura.

### Reglas

- consumir snapshots canonicos de `SessionController` y `NodeRegistry`;
- no leer widgets ni estado visual para recalcular salud;
- no duplicar la logica de `NodeStatus`;
- producir un snapshot de mapa estable y facil de testear.

## 8. Preparacion para Ticket 32.1

La implementacion siguiente debe apoyarse en contratos puros para:

- snapshot de Home;
- agregacion por caja;
- secciones primarias de shell;
- sincronizacion de seleccion entre Home y `Nodos`.
