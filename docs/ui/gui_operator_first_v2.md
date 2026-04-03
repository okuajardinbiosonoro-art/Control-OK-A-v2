# GUI Operator-First CKv2 v2

## 1. Resumen ejecutivo

La app local de CKv2 deja de tratarse como una suma de vistas técnicas separadas y pasa a organizarse como una superficie de operación principal guiada por mapa.

La regla congelada de esta fase es:

- la home principal vive en la app local de escritorio;
- el mapa operativo principal vive en la app local de escritorio;
- la consola web remota sigue siendo una superficie complementaria para acceso desde celular/navegador;
- las vistas técnicas siguen existiendo, pero quedan reordenadas y encapsuladas bajo una navegación más clara.

El objetivo de la GUI final local ya no es “exponer todo el estado técnico al frente”, sino:

- permitir arrancar y detener operación rápido;
- mostrar el estado general del sistema en una sola lectura;
- convertir el mapa en el centro de la experiencia;
- reservar el detalle técnico para superficies secundarias;
- y reducir la sensación de herramienta interna/modular desconectada.

## 2. Diagnóstico de la GUI actual

### 2.1 Lo que ya está bien

- Existe una base sólida de runtime real: sesión, NodeRegistry, control-plane F3, firmware manager, OTA, herramientas avanzadas y servicio remoto.
- La vista `Nodos en vivo` ya agrupa por cajas y da una base útil para topología.
- `Control F3` ya está separado como superficie técnica especializada.
- `Firmware Manager` ya funciona como workspace técnico relativamente completo.
- `Herramientas avanzadas` ya consolidan configuración, servicio remoto y MIDI.

### 2.2 Problemas UX actuales

- La pestaña principal actual (`Sesión`) sigue siendo demasiado textual y demasiado explicativa para una home operator-first.
- La jerarquía visual actual privilegia resumen técnico y bloques de formulario antes que lectura operacional.
- `Estado actual` sigue existiendo como diálogo aparte, lo que duplica información y corta continuidad.
- `Herramientas avanzadas` siguen siendo modales, lo que da sensación de “encierro”.
- `Firmware Manager` ya es útil, pero todavía se entra a él como herramienta externa, no como sección natural del producto.
- La app mezcla lenguaje operativo con lenguaje técnico en superficies que no deberían hacerlo.
- La shell actual está organizada más por módulos internos del sistema que por prioridades reales del operador.

### 2.3 Consecuencia práctica

Hoy la app puede operar técnicamente bien, pero la GUI todavía se siente más cercana a:

- consola técnica de soporte,
- suite interna de herramientas,
- o prototipo consolidado,

que a un producto de operación de campo centrado en mapa, estado global y acciones rápidas.

## 3. Navegación final propuesta

## 3.1 Criterio general

La shell final local deja de depender de una única barra de tabs horizontales planas como estructura completa y evoluciona a una navegación jerárquica con una capa primaria clara y una capa secundaria para lo técnico.

## 3.2 Shell principal congelada

La navegación primaria final recomendada queda así:

- `Mapa`
- `Operación`
- `Nodos en vivo`
- `Firmware`
- `Técnico`

### Justificación

- `Mapa` debe ser la home y la primera pestaña real del operador.
- `Operación` mantiene el control del ciclo de sesión, pero deja de ser la home.
- `Nodos en vivo` sigue siendo la tabla/lista canónica.
- `Firmware` merece superficie propia y persistente; deja de sentirse “herramienta aparte”.
- `Técnico` agrupa lo que hoy está demasiado disperso o modal.

## 3.3 Navegación secundaria congelada

Dentro de `Técnico`, la navegación secundaria queda:

- `Estado técnico`
- `Control F3`
- `Herramientas`

Esto permite:

- reducir ruido en la navegación principal;
- mantener acceso total para técnico/admin;
- y evitar que el operador vea demasiadas superficies internas como primera capa.

## 3.4 Política modal / no modal

### Debe migrar fuera de modal

- `Estado actual` deja de existir como diálogo principal y su contenido se redistribuye entre `Mapa`, `Operación` y `Técnico`.
- `Herramientas avanzadas` migran a `Técnico > Herramientas`.
- `Firmware Manager` migra a `Firmware` como vista persistente.

### Puede seguir siendo modal

- selector de perfil en primer arranque o cambio sensible;
- confirmaciones destructivas;
- importadores de archivos;
- confirmaciones de OTA o reboot;
- mensajes críticos que requieren decisión explícita.

## 3.5 Qué significa esto para la implementación

La shell futura debe sentirse más parecida a una app profesional de operación:

- navegación persistente;
- cambio de superficie sin cerrar ventanas;
- contexto siempre visible;
- menos saltos entre diálogo y diálogo;
- más continuidad espacial.

## 4. Home principal operator-first

## 4.1 Regla central

La home principal local pasa a ser `Mapa`.

No debe abrir con:

- paneles largos de texto,
- resúmenes técnicos extensos,
- tablas como elemento protagonista,
- ni mensajes tipo variable/configuración como primera lectura.

## 4.2 Composición congelada de la home

La home `Mapa` debe contener, como mínimo:

- barra superior de operación;
- mapa operativo protagonista;
- resumen global muy corto;
- inspector compacto de selección;
- alertas operator-friendly no invasivas.

## 4.3 Barra superior de operación

Debe incluir:

- perfil activo;
- estado global de operación;
- botón principal `Iniciar operación` / `Detener operación`;
- indicador corto de control-plane;
- acceso visible a alertas recientes;
- acceso rápido a `Nodos en vivo`.

No debe incluir:

- bloques largos de explicación;
- rutas de config;
- variables internas;
- texto diagnóstico extenso.

## 4.4 Resumen global corto

La home solo debe mostrar 3-5 señales globales:

- estado de sesión;
- cajas sanas / esperadas;
- nodos conectados / esperados;
- control-plane disponible o no;
- alertas activas.

Todo el resto vive fuera de la home.

## 4.5 Qué se mueve fuera de la home

### Va a `Operación`

- detalle del lifecycle de sesión;
- readiness/preflight explicado;
- mensajes largos de inicio/parada;
- ajustes de operación.

### Va a `Nodos en vivo`

- tabla/lista canónica completa;
- PPS, pérdida, RSSI y métricas detalladas por nodo;
- lectura comparativa completa entre nodos.

### Va a `Técnico`

- runtime serial/UDP completo;
- diagnósticos;
- control-plane técnico;
- servicio remoto;
- config y MIDI;
- trazas técnicas.

## 5. Contrato del mapa operativo local

El contrato detallado del mapa queda en [map_contract_v1.md](c:\Users\JOSE DAVID\Desktop\OKÚA\Códigos\Aplicaciones\Control_Okua_v2\Control-OK-A-v2\docs\ui\map_contract_v1.md).

Reglas congeladas de alto nivel:

- el mapa es la vista resumida/operator-first;
- `Nodos en vivo` sigue siendo la vista canónica detallada;
- seleccionar una caja o nodo en el mapa debe sincronizar la selección con `Nodos en vivo`;
- el mapa no inventa una segunda fuente de verdad;
- el mapa se apoya en un asset/topología configurable, no en hardcode final.

## 6. Contrato de alertas operator-friendly

El contrato detallado de alertas y copy queda en [ux_copy_guidelines_v1.md](c:\Users\JOSE DAVID\Desktop\OKÚA\Códigos\Aplicaciones\Control_Okua_v2\Control-OK-A-v2\docs\ui\ux_copy_guidelines_v1.md).

Reglas congeladas:

- ubicación principal esperada: esquina inferior izquierda;
- formato toast apilado;
- lenguaje corto y entendible;
- semántica clara entre éxito, advertencia, error e informativo;
- nunca exponer nombres de variables o códigos internos en la home salvo necesidad real.

## 7. Política de lenguaje UX

## 7.1 Home `Mapa`

Usa lenguaje operativo.

Ejemplos permitidos:

- `Operación activa`
- `Caja 2 con advertencia`
- `3 nodos conectados`
- `Se perdió comunicación con una caja`

Ejemplos no permitidos como copy principal:

- `profile.active inválido`
- `bind_host no resuelto`
- `cmd_seq`
- `nonce`
- `resolution_status unresolved`

## 7.2 `Operación`

Usa lenguaje operativo con soporte técnico ligero.

Debe explicar:

- si la operación está lista;
- si puede iniciarse;
- por qué no puede iniciarse.

Puede mencionar conceptos como `sesión`, `preparación`, `control-plane`, pero con redacción humana.

## 7.3 `Nodos en vivo`

Usa lenguaje mixto:

- primariamente operativo;
- secundariamente técnico.

Aquí sí caben:

- RSSI;
- última nota;
- pérdida;
- PPS;
- uptime;

pero con etiquetas comprensibles.

## 7.4 `Técnico`

Acepta lenguaje técnico explícito.

Aquí sí puede aparecer:

- control-plane;
- F3;
- runtime UDP/serial;
- resolución de nodo;
- errores detallados;
- términos internos del protocolo.

## 7.5 `Firmware`

Debe usar lenguaje técnico productizado.

Ejemplos:

- `Firmware actual`
- `Artifact`
- `Versión`
- `Deploy OTA`
- `Canary`

Evitar jerga críptica innecesaria, pero no ocultar vocabulario técnico que aquí sí corresponde.

## 8. Base visual y paleta para software

## 8.1 Fuente base de decisión

En esta sesión no apareció un PDF de marca accesible como archivo del workspace. La propuesta visual se apoya en:

- el icono actual de la app;
- el tema actual en [theme.qss](c:\Users\JOSE DAVID\Desktop\OKÚA\Códigos\Aplicaciones\Control_Okua_v2\Control-OK-A-v2\gui\theme.qss);
- y la topología del plano suministrada por el usuario.

La validación final contra manual de marca queda congelada para `34.0`.

## 8.2 Paleta base recomendada

### Colores estructurales

- `Graphite shell`: `#252525`
- `Secondary dark surface`: `#2D2D2D`
- `Warm light surface`: `#F2EFE4`
- `Primary text on dark`: `#F5F3EC`
- `Primary text on light`: `#1F2A2A`

### Colores de identidad / producto

- `Circuit teal`: `#2FACC6`
- `Deep leaf green`: `#214631`
- `Warm gold accent`: `#D6B25A`

### Colores semánticos de estado

- `Healthy`: `#3DAE6A`
- `Calibrating`: `#2FACC6`
- `Warning`: `#D89A2B`
- `Critical`: `#C54E4E`
- `Muted / unknown`: `#6E7471`

Regla congelada:

- los colores de estado no deben confundirse con los colores corporativos;
- `teal` se reserva para interacción/identidad y `calibrating`;
- el dorado se usa como acento de marca, no como semántica de error.

## 8.3 Tipografía base

Recomendación de software:

- fuente principal UI: `Segoe UI` en Windows con fallback empaquetado futuro a `Noto Sans`;
- fuente de branding: solo para splash, portada o títulos muy puntuales;
- nunca usar la tipografía de branding como base de tablas, paneles o tool panes.

## 8.4 Spacing y densidad

Congelar estas reglas base:

- grid de 8 px;
- padding principal de panel: 16-24 px;
- targets mínimos clicables: 40-44 px;
- tarjetas compactas, no densidad extrema de texto;
- alineación clara por columnas y bloques;
- nada de párrafos largos en home.

## 9. Robustez visual multi-equipo

Este trabajo queda congelado como línea obligatoria de `34.4`, pero sus riesgos se fijan aquí:

- fuentes no empaquetadas cambian métricas entre equipos;
- escalado DPI rompe anchos y cortes de texto;
- algunos assets pueden verse distintos según rendering de Windows;
- layouts basados en texto largo se degradan con facilidad;
- diálogos modales intensifican esa percepción de inconsistencia.

Reglas para futuras implementaciones:

- empaquetar fuentes críticas o usar fallback muy controlado;
- probar 100%, 125% y 150% DPI;
- usar labels con wrap y elide explícitos;
- evitar layouts que dependan del ancho exacto de un string;
- probar el `.exe` en al menos dos equipos distintos antes del cierre visual.

## 10. Riesgos y decisiones pendientes

- validar la propuesta visual final contra el PDF/manual de marca adjunto cuando esté accesible en el trabajo de 34.0;
- decidir si la shell final usa rail lateral o tabs estilizadas como implementación concreta;
- decidir si el inspector de la home será panel lateral fijo o panel contextual plegable;
- decidir el asset final del plano y su formato fuente;
- normalizar la política final de iconografía.

## 11. Roadmap inmediato congelado

### Serie 32.x — shell y UX local

- `32.1 Shell principal y navegación no modal`
  - migrar de la shell actual a la estructura primaria `Mapa / Operación / Nodos en vivo / Firmware / Técnico`.
- `32.2 Home operator-first`
  - convertir la home local en superficie de mapa, estado corto y acción rápida.
- `32.3 Limpieza de lenguaje y textos`
  - separar copy de operario vs copy técnico.
- `32.4 Robustez visual multi-equipo`
  - atacar paridad de `.exe`, layout, fuentes y DPI.

### Serie 33.x — mapa local

- `33.0 Asset del plano + contrato de coordenadas`
  - formalizar asset fuente, slots, anchors y datos configurables.
- `33.1 Mapa estático con cajas`
  - llevar el plano base a la home local.
- `33.2 Estado agregado por caja`
  - implementar semántica visual por caja.
- `33.3 Expansión compacta por caja`
  - panel/lista compacta de nodos por caja.
- `33.4 Sincronización mapa ↔ nodos`
  - selección cruzada entre mapa y `Nodos en vivo`.
- `33.5 Refresco live controlado`
  - actualización temporal controlada sin ruido ni saturación.

### Serie 34.x — design system y cierre visual

- `34.0 Design system CKv2`
  - tokens, paneles, espaciado, superficies y reglas visuales.
- `34.1 Alertas emergentes operator-friendly`
  - toasts y sistema de notificación final.
- `34.2 Icono, splash y branding puntual`
  - aterrizar identidad visual de producto.
- `34.3 Pulido visual de tabs/widgets`
  - homogeneizar componentes de toda la app.
- `34.4 Paridad visual del .exe`
  - cerrar diferencias entre equipos.
- `34.5 QA final operator-first`
  - prueba integral de usabilidad y consistencia.

## 12. Decisión final congelada

La app local de CKv2 queda definida como:

- superficie principal de operación;
- home guiada por mapa;
- navegación jerárquica y menos modal;
- lenguaje operator-first en primera capa;
- detalle técnico preservado pero reubicado;
- y evolución explícita hacia producto de campo, no solo herramienta técnica interna.
