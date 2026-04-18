# Ensayo de entrega interna 36.1 — reproducibilidad operativa

Rama: `desarrollo-fase-2`
Fecha: 2026-04-18
Objetivo: verificar que la Release Interna Controlada se puede reproducir en una copia limpia sin depender de contexto oral.

---

## 1. Entorno usado

| Campo | Valor |
|------|-------|
| Tipo de entorno | Copia limpia del repositorio en `%TEMP%\okua_rehearsal_clean` |
| Sistema operativo | Microsoft Windows 11 Home Single Language |
| Versión de Windows | 10.0.26200, 64 bits |
| Python | 3.11.0 |
| Plataforma Qt durante el ensayo | `QT_QPA_PLATFORM=offscreen` |
| Perfil usado para el arranque no interactivo | `udp_jardin` |
| Ruta de trabajo | `C:\Users\JOSE DAVID\AppData\Local\Temp\okua_rehearsal_clean` |

La copia limpia se obtuvo con `git clone --no-hardlinks . %TEMP%\okua_rehearsal_clean` desde la rama `desarrollo-fase-2`.

---

## 2. Instalación reproducida desde cero

### Pasos ejecutados

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

### Dependencias necesarias

- `PySide6`
- `pyserial`
- `mido`
- `python-rtmidi`
- `pyinstaller` para build
- `pytest` para la validación automática del ensayo

### Hallazgo de instalación

`pytest` no venía en el entorno de runtime. Para validar el ticket hubo que instalarlo aparte en la copia limpia. Eso no afecta el arranque de la app, pero sí es un paso implícito que conviene recordar si se quiere repetir el ensayo completo.

---

## 3. Ensayo de arranque

### Comandos ejecutados

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CKV2_AUTOPROFILE = 'udp_jardin'
python main.py
```

La app se lanzó desde la raíz de la copia limpia y creó `config.json` automáticamente porque no existía.

### Resultado de arranque

- `config.json` fue creado en el primer arranque.
- `profile.active` quedó resuelto a `udp_jardin`.
- `remote_api` permaneció deshabilitado.
- La ventana principal abrió sin traceback.
- El resumen de preflight quedó en estado `ready`.

### Warnings observados

- Mensaje de Qt sobre directorio de fuentes en el venv.
- Mensaje de `propagateSizeHints()` del plugin offscreen.
- Aviso no bloqueante de MIDI porque `loopMIDI Port 3` no estaba presente en esta máquina.

Ninguno de esos avisos bloqueó la apertura ni el uso básico.

---

## 4. Flujo básico validado

### Home y navegación

Se validó la ventana real en offscreen con estos resultados:

- `title=Control OKÚA · CKv2`
- `initial_tab=Inicio`
- `initial_shell=Inicio`
- `home_has_map=True`
- navegación a `Nodos`, `Diagnóstico` y `Técnico` correcta
- retorno a `Inicio` correcto
- cierre limpio correcto

### Salida de navegación comprobada

```text
after_nodes=tab:Nodos;shell:Nodos
after_diagnostics=tab:Diagnóstico;shell:Diagnóstico
after_technical=tab:Técnico;shell:Técnico
return_home=Inicio;shell=Inicio
closed=True
```

### Sesión básica semirreal

Con la app abierta y `udp_jardin` activo:

- el estado inicial fue `idle`
- el chip mostró `Estado de sesión: inactiva`
- la sesión subió a `running`
- fue posible navegar a `Nodos`, `Diagnóstico` y `Técnico` con la sesión viva
- la sesión volvió a `idle` al detenerla

### Salida de sesión comprobada

```text
initial_state=idle
after_start_state=running
nav_nodes=Nodos;shell=Nodos
nav_diag=Diagnóstico;shell=Diagnóstico
nav_tech=Técnico;shell=Técnico
after_stop_state=idle
closed=True
```

Además, el backend MIDI resolvió correctamente los buses 0 y 1 contra los nombres visibles de la máquina. El bus 2 quedó sin puerto disponible, pero eso no impidió el arranque de la sesión.

---

## 5. Qué funcionó de primera

- Instalación de dependencias de runtime.
- Creación automática de `config.json`.
- Arranque con `python main.py`.
- Perfil operativo `udp_jardin`.
- Apertura de Home.
- Navegación mínima a `Nodos`, `Diagnóstico` y `Técnico`.
- Inicio y detención de una sesión UDP semirreal.
- Cierre limpio de la app.

---

## 6. Qué no funcionó de primera

- `pytest` no estaba instalado en el entorno limpio.
- `loopMIDI Port 3` no estaba disponible en la máquina.
- El primer arranque limpio necesita que el perfil quede explícito, ya sea por selector guiado o por `CKV2_AUTOPROFILE=udp_jardin`.

---

## 7. Ajustes necesarios

- Instalación manual de `pytest` para validar el ensayo.
- Documentación adicional del primer arranque limpio en el runbook, checklist, handoff y README.
- Confirmación explícita de que `CKV2_AUTOPROFILE=udp_jardin` es la ruta no interactiva para una copia limpia.

---

## 8. Bugs / fricciones de reproducibilidad

- Falta de explicitación del primer arranque limpio en la documentación operativa.
- Dependencia de validación (`pytest`) ausente del venv de runtime.
- Aviso de MIDI por bus 2 ausente, sin impacto funcional.

No hubo bugs funcionales que obligaran a cambiar código de la aplicación.

---

## 9. Decisión final

La entrega interna **sí es reproducible** en una copia limpia, con una condición operativa clara: el primer arranque debe dejar explícito el perfil de uso. Para un arranque no interactivo, la ruta validada fue:

```powershell
$env:CKV2_AUTOPROFILE = 'udp_jardin'
python main.py
```

Con eso, la app abrió, navegó Home/Nodos/Diagnóstico/Técnico y pudo iniciar y detener una sesión UDP semirreal sin depender de contexto oral.
