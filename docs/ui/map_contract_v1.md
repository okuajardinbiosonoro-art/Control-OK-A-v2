# Contrato del mapa operativo local v1

> Nota: este documento queda como antecedente exploratorio. El contrato canonico congelado para Ticket 32.0 vive en [desktop_shell_operator_first.md](desktop_shell_operator_first.md) y [home_map_state_contract.md](home_map_state_contract.md).

## 1. Propósito

Definir el contrato funcional y espacial del mapa principal de la app local de escritorio.

Este documento no implementa todavía el widget final; congela:

- semántica espacial;
- estados agregados por caja;
- interacción por caja y por nodo;
- sincronización con `Nodos en vivo`;
- y criterios de compactación operator-first.

## 2. Regla de producto

El mapa principal vive en la app local de escritorio.

No vive en la consola web remota.

La consola web remota puede seguir teniendo vistas resumidas, pero el plano principal y su experiencia de operación pertenecen a la GUI local.

## 3. Topología base congelada

La topología funcional inicial se define así:

- `Caja 1`: centro, 2 nodos
- `Caja 2`: lateral izquierda alta, 5 nodos
- `Caja 3`: lateral izquierda baja, 5 nodos
- `Caja 4`: parte superior, 5 nodos
- `Caja 5`: lateral derecha, 5 nodos

## 3.1 Lectura del plano adjunto

El plano suministrado marca una composición tipo isla/pera con un punto central y cuatro puntos periféricos.

La lectura UX congelada es:

- `Caja 1` se ancla al centro del plano;
- `Caja 4` se ancla al punto superior;
- `Caja 2` se ancla al lateral izquierdo alto;
- `Caja 3` se ancla al lateral izquierdo bajo;
- `Caja 5` se ancla al lateral derecho medio-bajo.

No se congelan todavía coordenadas pixel-perfect.

Sí se congela:

- la posición relativa;
- el orden espacial;
- y la expectativa de que el plano futuro salga desde un asset, no desde hardcode visual final.

## 4. Fuente de verdad

El mapa no crea una segunda fuente de verdad.

Se alimenta de:

- snapshots canónicos de nodos;
- reglas canónicas de identidad/caja;
- y el mismo runtime ya usado por `Nodos en vivo`.

## 5. Estado agregado por caja

## 5.1 Objetivo

Cada caja debe responder visualmente:

- si está sana;
- si está en calibración;
- si está parcialmente degradada;
- o si está en fallo crítico.

## 5.2 Semántica agregada congelada

### Verde — sana/completa

Usar cuando:

- todos los nodos esperados de la caja están presentes;
- no hay nodos `degraded`;
- no hay nodos `offline`;
- y no hay calibración activa.

### Cian / teal — calibrating

Usar cuando:

- hay al menos un nodo `calibrating`;
- no hay nodos `degraded`;
- y no hay fallo crítico.

Esto separa el estado de arranque/calibración de una falla real.

### Amarillo / naranja — parcialmente degradada

Usar cuando:

- existe al menos un nodo `degraded`;
- o faltan nodos esperados, pero todavía hay actividad parcial útil;
- o la caja no está completa, pero tampoco está caída en bloque.

### Rojo — fallo crítico

Usar cuando:

- todos los nodos esperados están offline;
- o la caja quedó sin actividad útil;
- o la pérdida operativa de la caja es total o casi total.

### Gris / neutro — sin datos

Usar cuando:

- aún no hay sesión activa;
- o todavía no hay evidencia suficiente para clasificar.

## 5.3 Apoyo visual obligatorio

El color no basta.

Cada caja debe mostrar además:

- `conectados / esperados`
- y, si aplica, una etiqueta corta de estado (`Sana`, `Calibrando`, `Parcial`, `Crítica`).

## 6. Interacción principal

## 6.1 Click sobre caja

Primer click:

- selecciona la caja;
- resalta su contorno;
- muestra expansión compacta o panel asociado;
- actualiza el inspector de la home.

Segundo click sobre la misma caja:

- colapsa la expansión compacta;
- mantiene el estado global del mapa sin ruido.

## 6.2 Click sobre nodo dentro de caja

Debe:

- seleccionar el nodo;
- actualizar el inspector o detalle compacto de home;
- sincronizar la selección en `Nodos en vivo`.

No debe:

- abrir una segunda interfaz desconectada;
- disparar navegación sorpresiva;
- ni perder contexto del mapa.

## 6.3 Relación con `Nodos en vivo`

`Nodos en vivo` sigue siendo la vista canónica detallada.

El mapa:

- resume;
- orienta;
- y acelera la selección.

La regla congelada es:

- mapa e `Nodos en vivo` comparten selección;
- la selección de uno debe reflejarse en el otro;
- el mapa nunca reemplaza la tabla/lista técnica.

## 7. Contrato de expansión compacta por caja

La expansión compacta por caja debe mostrar, por nodo:

- identidad corta (`EB1`, `EC3`, etc.);
- estado visual;
- última nota útil o `—`;
- indicador de RSSI/potencia;
- señal de frescura/actividad reciente si sale barato.

## 7.1 Lo que no debe entrar en la expansión compacta

No mostrar aquí:

- PPS completos;
- pérdida detallada;
- variables del control-plane;
- mensajes de error largos;
- bloques OTA extensos;
- campos tipo debug.

Eso queda para `Nodos en vivo` o `Técnico`.

## 7.2 Política de densidad

La expansión por caja debe ser breve y escaneable.

Meta UX:

- lectura en 2-4 segundos;
- sin scroll interno si no es estrictamente necesario;
- sin parecer tabla miniaturizada.

## 8. Estados vacíos

## 8.1 Sin sesión o sin datos

El mapa debe mostrar estado vacío claro:

- sin cajas falsas “en verde”;
- sin nodos fantasmas;
- sin layout roto.

Mensaje esperado:

- `Aún no hay operación activa`
- o `Todavía no hay nodos visibles`

## 8.2 Caja sin nodos visibles

Debe verse como caja vacía o sin actividad:

- con color neutro o crítico según el contexto runtime;
- pero sin saturar la home con mensajes repetidos.

## 9. Responsive local desktop

Aunque la superficie principal es desktop, el mapa debe soportar:

- ventanas reducidas;
- split panes;
- escalado alto;
- y densidad visual razonable.

Reglas:

- targets amplios;
- no depender de hover;
- labels cortos;
- layout que sobreviva al resize.

## 10. Contrato de datos futuro

La implementación futura debe poder leer una definición de plano/config con esta forma conceptual:

```json
{
  "map_id": "jardin_v1",
  "background_asset": "assets/maps/jardin_v1.png",
  "boxes": [
    {
      "box_id": 1,
      "label": "Caja 1",
      "expected_nodes": 2,
      "position_slot": "center",
      "node_order": ["EB1", "EB2"]
    }
  ]
}
```

No se congela todavía el formato exacto final, pero sí estos campos conceptuales:

- `box_id`
- `label`
- `expected_nodes`
- `position_slot` o coordenadas equivalentes
- `node_order`
- `background_asset`

## 11. Qué queda explícitamente fuera

- overlay live avanzado;
- animaciones complejas;
- editor visual de plano;
- drag and drop;
- coordenadas libres editables por usuario;
- mapa web remoto como superficie principal.

## 12. Decisión final congelada

El mapa local de CKv2 será:

- la home principal operator-first;
- una vista resumida basada en cajas;
- sincronizada con `Nodos en vivo`;
- con estado agregado razonado;
- y con expansión compacta por caja en lugar de tabla disfrazada.
