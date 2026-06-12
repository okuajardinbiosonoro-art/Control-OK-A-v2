# Promoción a main — Control OKÚA CKv2 — RC1 Interna

Rama origen: `desarrollo-fase-2`
Fecha: 2026-04-19 (Ticket 39.0)
Estado: **PROMOVIDA — fast-forward limpio**

---

## Bloque 1 — Auditoría previa

| Ítem | Resultado |
|------|-----------|
| `git fetch origin` | Ejecutado — remoto sincronizado |
| HEAD de `main` antes de promover | `7fe065d` (Ticket 10: responsive Nodos…) |
| HEAD de `desarrollo-fase-2` | `6a16c33` (docs 38.0: aceptación operativa interna) |
| Merge base entre ambas ramas | `7fe065d` — coincide con HEAD de `main` |
| Commits en `desarrollo-fase-2` no en `main` | **139** |
| Commits en `main` no en `desarrollo-fase-2` | **0** |
| Tipo de promoción posible | **Fast-forward limpio** — sin divergencia |
| Working tree sucio en código | NO — solo `.vscode` CRLF (conocido), untracked de firmware/memoria |
| Deuda bloqueante abierta | NO — clasificada como no bloqueante en 38.0 |
| Estado de aceptación operativa | VIGENTE — emitida en 38.0 (2026-04-19) |

---

## Bloque 2 — Ejecución de la promoción

### Comando ejecutado

```bash
git push origin desarrollo-fase-2:main
```

### Resultado

```
7fe065d..6a16c33  desarrollo-fase-2 -> main
```

- **Tipo:** Fast-forward limpio
- **Commit anterior de main:** `7fe065d`
- **Commit final de main:** `6a16c33`
- **139 commits** integrados en `main`

---

## Bloque 3 — Tag de release interna

### Tag creado

| Campo | Valor |
|-------|-------|
| Nombre | `rc1-interna` |
| Tipo | Annotated tag |
| Commit referenciado | `6a16c33` |
| Rama | `main` (y `desarrollo-fase-2` — mismo commit) |
| Push a origin | **EXITOSO** |

### Contenido del tag

```
Release Interna Controlada RC1 — Control OKÚA CKv2
Estado: ACEPTADA para operación interna controlada (Ticket 38.0, 2026-04-19)
Validaciones: sesión UDP real, OTA hardware, portal remoto, suite 498/498,
              observación real 690 s, aceptación formal.
Ruta principal: python main.py
Ruta secundaria: dist/Control OKÚA CKv2/Control OKÚA CKv2.exe
```

---

## Bloque 4 — Estado final de ramas

| Rama | HEAD | Observación |
|------|------|-------------|
| `main` | `6a16c33` | Promovida — coincide con `desarrollo-fase-2` |
| `desarrollo-fase-2` | `6a16c33` | Sin cambios — rama de trabajo activa |
| Tag `rc1-interna` | `6a16c33` | Publicado en origin |

---

## Bloque 5 — Documentos que sustentan la promoción

| Documento | Propósito |
|-----------|----------|
| `docs/ui/internal_operational_acceptance.md` | Aceptación operativa formal (38.0) |
| `docs/ui/internal_release_checklist.md` | Checklist de entrega interno completo |
| `docs/ui/internal_release_notes_rc1.md` | Release notes de RC1 |
| `docs/ui/release_candidate_handoff.md` | Evidencia completa de validación RC |
| `docs/ui/internal_operational_observation_real.md` | Observación real 37.2 con nodos físicos |

---

## Bloque 6 — Rollback de la promoción

Si la promoción necesita revertirse:

```bash
# Revertir main al commit anterior
git push origin 7fe065d:main --force-with-lease

# Eliminar el tag si también debe revertirse
git push origin :rc1-interna
git tag -d rc1-interna
```

> El commit `7fe065d` es el estado de `main` inmediatamente antes de esta promoción.
> `desarrollo-fase-2` **no se ve afectada** por revertir `main`.

---

## Decisión final

**La promoción a `main` se ejecutó correctamente como fast-forward limpio.**
**El tag `rc1-interna` queda publicado como referencia trazable de la Release Interna Controlada RC1.**
`main` ahora refleja el estado operativamente aceptado y documentado de Control OKÚA CKv2.
