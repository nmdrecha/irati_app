# Irati — Comprobación de facturación (Quirón vs Real)

Aplicación web (Streamlit) con dos pasos:

1) **Transformación Quirón → (historia, código)** usando la **tabla fija de referencia** (pestaña *Irati*).
2) **Comparación** contra el Excel de facturación **Real** (anti-join: lo que está en Real y no en Quirón transformado).
   
## Cómo ejecutar

```bash
pip install -r requirements.txt
streamlit run app.py
```

La app creará/leerá la tabla fija desde `data/TABLA_CODIGOS_DE_FACTURACION.xlsx`.
Puedes actualizarla en la pestaña **Irati** (se guarda en `data/` para futuras sesiones).
