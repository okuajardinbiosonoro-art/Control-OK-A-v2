# Desktop Shell Operator-First CKv2

## 1. Proposito de la nueva shell

Este documento congela el contrato UI/UX de la futura shell desktop principal de Control OKUA v2 para el Ticket 32.0.

La shell futura debe:

- abrir en una Home operator-first;
- usar el mapa/plano como lectura principal del sistema;
- mantener una ruta clara hacia el detalle tecnico sin saturar la Home;
- reutilizar el runtime real ya existente;
- preparar la implementacion del Ticket 32.1 sin improvisacion de arquitectura.

Este documento es el contrato canonico para la shell operator-first. La GUI actual puede seguir en estado transicional mientras se implementan los tickets siguientes.

## 2. Motivacion del cambio

CKv2 ya cuenta con una base operativa valida:

- `SessionController` real;
- runtime serial y UDP;
- `NodeRegistry` y politicas de estado;
- panel tecnico y control-plane F3;
- gestion de firmware y OTA;
- servicio remoto y consola web.

La siguiente evolucion del producto no consiste en agregar mas backend, sino en reorganizar la experiencia desktop para que la operacion diaria empiece desde una lectura espacial del sistema y no desde paneles tecnicos.

## 3. Principios de diseno

- `operator-first`: la primera lectura debe responder "que esta pasando y donde".
- `desktop-first`: la app local es la superficie principal de operacion.
- `single source of truth`: la shell no crea una segunda verdad distinta al runtime.
- `progressive disclosure`: la Home resume y orienta; el detalle vive en superficies secundarias.
- `technical containment`: firmware, OTA, control-plane y mantenimiento no contaminan la Home.
- `safe evolution`: la implementacion puede avanzar por tickets sin romper la UI actual.

## 4. Superficies principales del producto

La shell desktop futura queda congelada con cinco superficies principales:

1. `Home / Mapa`
2. `Nodos`
3. `Diagnostico`
4. `Firmware / OTA`
5. `Herramientas avanzadas`

### Regla de navegacion

- `Home / Mapa` es la primera superficie al abrir la app.
- `Nodos` es la superficie de inspeccion tecnico-operativa principal.
- `Diagnostico` concentra eventos, observabilidad y soporte.
- `Firmware / OTA` vive como superficie tecnica separada.
- `Herramientas avanzadas` agrupa control-plane, configuracion delicada y mantenimiento.

### Relacion con la shell actual

- La `MainWindow` actual puede conservar sus tabs y dialogos mientras la migracion no haya ocurrido.
- El contrato congelado para la shell futura es el descrito aqui, no la disposicion transicional actual.
- El Ticket 32.0 no obliga a reescribir la navegacion activa; obliga a dejar claro el destino y sus limites.

## 5. Home operator-first guiada por mapa

`Home / Mapa` queda definida como la vista principal operator-first de CKv2.

### Debe hacer

- mostrar una lectura espacial del sistema guiada por mapa/plano;
- resumir el estado operativo por caja;
- exponer un resumen global corto;
- ofrecer acciones rapidas de operacion;
- permitir acceso contextual a detalle;
- orientar al operador hacia la caja o nodo que requiere atencion.

### No debe hacer

- reemplazar la tabla detallada de nodos;
- convertirse en un panel tecnico saturado;
- mostrar workflows de firmware/OTA;
- exponer controles delicados de mantenimiento como contenido primario;
- duplicar vistas de diagnostico o tooling avanzado.

### Composicion minima congelada

La Home futura debe poder componerse con estos bloques:

- barra superior de operacion;
- mapa operativo protagonista;
- resumen global compacto;
- inspector contextual compacto para caja o nodo seleccionado;
- acceso corto a alertas activas.

### Barra superior de operacion

La barra superior de Home puede incluir:

- perfil activo;
- estado de sesion;
- accion principal `Iniciar` / `Detener`;
- salud global resumida;
- acceso rapido a `Nodos`.

La barra superior no debe incluir:

- rutas de configuracion;
- parametros internos del runtime;
- trazas largas;
- formularios tecnicos extensos.

## 6. Pestana Nodos como vista de detalle

`Nodos` queda congelada como la vista de detalle tecnico-operativo principal.

### Rol

- tabla detallada por nodo;
- verdad operativa detallada;
- metricas amplias;
- razones de estado;
- inspeccion fina por nodo y por caja.

### Regla de producto

- La Home resume y orienta.
- `Nodos` detalla y confirma.
- La Home no reemplaza `Nodos`.
- `Nodos` no reemplaza la lectura espacial de la Home.

## 7. Diagnostico

`Diagnostico` queda reservada para soporte, observabilidad y troubleshooting.

### Debe concentrar

- eventos relevantes;
- problemas de readiness;
- problemas de backend/runtime;
- observabilidad de transporte;
- mensajes tecnicos necesarios para soporte.

### No debe hacer

- reemplazar la tabla detallada de `Nodos`;
- convertirse en la Home;
- duplicar workflows de herramientas avanzadas.

## 8. Firmware / OTA

`Firmware / OTA` queda congelada como superficie tecnica separada.

### Rol

- catalogo de artefactos;
- importacion, validacion y seleccion de firmware;
- despliegues OTA;
- seguimiento de campañas;
- gates y resultados tecnicos de actualizacion.

### Regla de contencion

- La Home puede mostrar solo resumenes o badges que deriven hacia `Firmware / OTA`.
- Los workflows completos de firmware y OTA no viven en la Home.

## 9. Herramientas avanzadas

`Herramientas avanzadas` queda congelada como la superficie para acciones delicadas y administracion tecnica.

### Incluye

- control-plane F3;
- ajustes avanzados;
- configuracion remota;
- mantenimiento;
- herramientas de soporte especializadas.

### Regla de visibilidad

- siguen siendo parte del producto;
- no se muestran como contenido dominante en la Home;
- deben requerir navegacion deliberada;
- las acciones peligrosas mantienen confirmaciones y resguardos.

## 10. Relacion con consola web

La relacion desktop vs web queda congelada asi:

- la app desktop es la herramienta principal local;
- la consola web es complementaria;
- la consola web no reemplaza la Home del desktop;
- el desktop sigue siendo el centro visual y operativo local.

### Implicaciones

- el mapa principal vive en desktop;
- la web puede ofrecer monitoreo resumido y acceso remoto complementario;
- la web no define la arquitectura principal de navegacion de la app local.

## 11. Modelo de estados visuales

La Home y el mapa usan cuatro estados operativos minimos, reutilizando la semantica de estado del runtime:

- `online`
- `calibrating`
- `degraded`
- `offline`

La semantica detallada y la politica de agregacion por caja se complementan en [home_map_state_contract.md](home_map_state_contract.md).

### Regla clave

- la shell no inventa estados nuevos paralelos al runtime;
- la representacion visual puede tener un placeholder neutro "sin datos" antes de la primera evidencia de runtime, pero ese placeholder no reemplaza ni redefine los cuatro estados operativos.

## 12. Estado agregado por caja

La politica congelada para la caja es "peor estado operativo util", con la siguiente prioridad:

1. `offline`
2. `degraded`
3. `calibrating`
4. `online`

### Reglas

- si toda la caja carece de actividad util, la caja es `offline`;
- si hay actividad parcial, nodos faltantes o degradacion parcial, la caja es `degraded`;
- si no hay degradacion ni perdida total, pero existe calibracion activa, la caja es `calibrating`;
- solo es `online` cuando la caja esta completa y saludable;
- antes de tener snapshot util, la UI puede renderizar un placeholder neutro no operativo.

## 13. Estrategia de integracion con runtime

La integracion futura con runtime queda congelada con estas reglas:

- la Home no lee directamente todos los objetos internos del runtime;
- se introduce una capa adapter/view-model/snapshot UI-friendly;
- `SessionController` y `NodeRegistry` se reutilizan como fuente de verdad;
- no se crea una segunda verdad de estado;
- la agregacion por caja sucede en una capa de presentacion pura y testeable.

### Flujo esperado

1. `SessionController` expone snapshots canonicos de sesion y nodos.
2. Un adapter de UI deriva un snapshot de Home orientado a mapa.
3. El mapa consume ese snapshot ya resumido.
4. La seleccion de Home y `Nodos` comparte identidad, no fuentes de verdad distintas.

## 14. Fuera de alcance del Ticket 32.0

Este ticket no implementa:

- el mapa vivo final;
- overlays finales;
- zoom/pan/hover definitivo;
- reescritura profunda de `MainWindow`;
- reestructuracion del runtime;
- nuevas logicas OTA o remotas;
- branding final, animaciones o polish profundo.

## 15. Preparacion para Ticket 32.1

El Ticket 32.1 queda preparado para:

- crear el primer contenedor real de `Home / Mapa`;
- conectar un adapter de snapshots entre runtime y Home;
- renderizar cajas y nodos con estado agregado;
- enlazar seleccion Home <-> `Nodos`;
- migrar gradualmente la shell actual hacia la navegacion congelada.

### Artefactos esperados para esa fase

- view-model de Home basado en snapshots;
- widget/view de mapa desktop;
- integracion controlada con la navegacion real;
- pruebas UI y de seleccion cruzada.
