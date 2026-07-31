# Certificados de este directorio (Plan 276)

## Los dos archivos

| Archivo | Qué contiene | Medido |
|---|---|---|
| `ca-bundle-migrador.pem` | Todas las CAs públicas de `certifi` **+ la HOJA de srvcgit01** | 119 certificados: 118 CA + **1 hoja** |
| `srvcgit01-hoja.pem` | **Solo la HOJA** de `srvcgit01.imsolutions.local` | 1 certificado, **0 CA** |

## Hoja vs CA — por qué importa acá

El certificado **hoja** es el del servidor (`CN=srvcgit01.imsolutions.local`, `O=Ubimia`).
La **CA** es quien lo emitió (`CN=imsolutions.local`, `O=PFSTechSL`).
Normalmente se confía en la CA y ella avala a sus hojas. Acá eso **no se puede**: esa CA
no está en ningún almacén de la máquina (barrido de `ROOT`+`CA` de Windows: 0 hits) y el
servidor manda **un solo certificado**, sin la cadena. Hay que confiar en la hoja directamente.

**El archivo se llamaba `srvcgit01-ca.pem` y el nombre MENTÍA**: no hay ninguna CA adentro.
Ese nombre mandó a más de una persona a buscar un problema de cadena que no existía.

## Por qué hace falta `VERIFY_X509_PARTIAL_CHAIN`

Sin esa flag, OpenSSL exige llegar a un ancla **auto-firmada**: busca la emisora de la hoja,
no la encuentra y falla con `unable to get local issuer certificate` **aunque la hoja exacta
esté en el bundle**. `VERIFY_X509_PARTIAL_CHAIN` permite que una hoja presente en el bundle
actúe como ancla.

**No debilita nada**: es *pinning* (la hoja tiene que coincidir exactamente con la que
presenta el servidor, más estricto que confiar en una CA que puede emitir para cualquier
host), `verify_mode` sigue en `CERT_REQUIRED` y `check_hostname` sigue activo.

## La trampa que cuesta una jornada

Para verificar que un bundle cargó la hoja, usá **`cert_store_stats()`**, nunca
**`get_ca_certs()`**: el segundo devuelve solo los certificados que son CA, así que es
**ciego a las hojas**. Medido: para `srvcgit01-hoja.pem` devuelve **0 de 1**, y para
`ca-bundle-migrador.pem` **118 de 119**. Es exactamente por esto que `truststore` falla
contra este servidor (busca los certs del `verify=` con `get_ca_certs()`), y por eso la
sesión de GitLab usa un contexto OpenSSL propio: `backend/services/tls_openssl_context.py`.

## Vencimiento

`notAfter = Jun 14 2028`. Cuando se renueve hay que reemplazar los dos `.pem`. El día que
pase, el mensaje de `CaBundleInvalido` y los 4 sub-veredictos del check de tracker lo hacen
visible en 10 segundos en vez de en una jornada.
