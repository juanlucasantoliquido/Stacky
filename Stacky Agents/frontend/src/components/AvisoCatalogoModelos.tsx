import { useModelCatalog } from "../hooks/useModelCatalog";
import { describirOrigenCatalogo } from "../services/modelCatalogOrigin";
import { Button } from "./ui";

/** Plan 288 F9 — dice de dónde salió la lista de modelos que el operador está
 * mirando: la suya, la de respaldo, o una recortada — y por qué.
 *
 * COMPONENTE TONTO A PROPÓSITO: toda la decisión vive en
 * services/modelCatalogOrigin.ts, que es `.ts` puro y se prueba entero. Acá no
 * hay ninguna regla que valga la pena probar, porque en este repositorio no se
 * puede montar un componente en una prueba.
 *
 * Sin estilos escritos a mano ni colores en hexadecimal: los ratchets de deuda
 * cuentan por archivo. Si hiciera falta color, van las variables del tema que SÍ
 * existen (--accent, --success, --danger, --border, --text-primary, --bg-panel);
 * `--color-*` NO existe en este tema y dejaría el aviso invisible. */
export default function AvisoCatalogoModelos({ runtime }: { runtime: string }) {
  const { respuesta, refrescar } = useModelCatalog();
  const aviso = describirOrigenCatalogo(respuesta, runtime);

  if (aviso.nivel === "ok") return null;

  return (
    <p role="note" title={aviso.detalle}>
      {aviso.texto}{" "}
      <Button variant="ghost" size="sm" onClick={refrescar}>
        Volver a consultar
      </Button>
    </p>
  );
}
