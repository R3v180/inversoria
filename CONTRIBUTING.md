# Contributing To InversorIA

Thank you for your interest in improving InversorIA.

InversorIA is an open-source local trading research project licensed under Apache-2.0. Forks, experiments and private modifications are allowed under the license. Changes to the official repository, however, are accepted only after maintainer review and explicit approval.

## Contribution Policy

- Please open an issue or discussion before starting large changes.
- Pull requests are welcome, but they must be reviewed and approved by the maintainer before merge.
- No one should assume that a contribution will be merged automatically.
- The `main` branch is maintained by Olivier Hottelet, trading as OHCodex.
- By submitting a contribution, you agree that it is provided under the Apache-2.0 license unless a separate written agreement says otherwise.

## What Helps Most

- Clear bug reports with logs, screenshots and reproduction steps.
- Focused pull requests that solve one problem at a time.
- Tests or manual verification notes for trading, risk, configuration or UI changes.
- Documentation improvements that make the project safer and easier to understand.
- Security reports sent privately instead of opened as public issues.

## Safety Rules

- Do not include API keys, `.env` files, databases, logs with secrets or personal account data.
- Do not submit changes that weaken risk controls without explaining the trade-off.
- Do not add real-order automation paths that bypass existing confirmation, mode or guardrail logic.
- Keep simulation and real-mode behavior clearly separated and documented.

## Pull Request Checklist

- Describe the reason for the change.
- Mention whether it affects real trading, simulation, risk limits, config import/export or the AI assistant.
- Include screenshots for visible UI changes.
- Run the relevant checks you can run locally.
- Update `README.md` or other documentation when behavior changes.

---

# Contribuir A InversorIA

Gracias por tu interés en mejorar InversorIA.

InversorIA es un proyecto open source local de investigación y trading con licencia Apache-2.0. La licencia permite forks, experimentos y modificaciones privadas. Los cambios al repositorio oficial, sin embargo, solo se aceptan tras revisión y aprobación explícita del mantenedor.

## Política De Contribuciones

- Abre un issue o discusión antes de empezar cambios grandes.
- Los pull requests son bienvenidos, pero deben ser revisados y aprobados por el mantenedor antes de hacer merge.
- Nadie debe asumir que una contribución se aceptará automáticamente.
- La rama `main` la mantiene Olivier Hottelet, bajo el nombre comercial OHCodex.
- Al enviar una contribución, aceptas que se entrega bajo licencia Apache-2.0 salvo acuerdo escrito separado.

## Qué Ayuda Más

- Bugs claros con logs, capturas y pasos para reproducir.
- Pull requests pequeños que resuelven un problema concreto.
- Tests o notas de verificación manual para cambios de trading, riesgo, configuración o UI.
- Mejoras de documentación que hagan el proyecto más seguro y fácil de entender.
- Reportes de seguridad enviados en privado, no como issues públicos.

## Reglas De Seguridad

- No incluyas claves API, archivos `.env`, bases de datos, logs con secretos ni datos personales de cuenta.
- No envíes cambios que debiliten controles de riesgo sin explicar el motivo.
- No añadas rutas de órdenes reales que salten confirmaciones, modos o guardrails existentes.
- Mantén claramente separado y documentado el comportamiento de simulación y modo real.

## Checklist Para Pull Requests

- Describe el motivo del cambio.
- Indica si afecta a trading real, simulación, límites de riesgo, import/export de configuración o asistente IA.
- Incluye capturas si hay cambios visibles de UI.
- Ejecuta las comprobaciones relevantes que puedas correr localmente.
- Actualiza `README.md` u otra documentación si cambia el comportamiento.
