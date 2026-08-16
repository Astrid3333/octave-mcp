# BEM electromagnetismo -- notas para retomar (no implementado aun)

## Por que es distinto a fem_poisson2d
- Discretizacion SOLO del borde (curvas/superficies), no del volumen -- geometria
  de entrada cambia: en vez de rectangulo+grilla, es una lista de segmentos/paneles
  sobre el contorno de cada conductor.
- Matriz resultante es DENSA (cada panel interactua con todos los demas via la
  funcion de Green), no dispersa como en FEM -- CG no aplica.
- Integrales sobre cada panel tienen singularidad logaritmica cuando el punto de
  colocacion coincide con el panel que se integra -- necesita cuadratura especial
  (ej. sustitucion logaritmica) ademas de cuadratura Gauss estandar para el resto.
- Sistema resultante no es necesariamente simetrico -- solver denso (LU) en vez
  de CG. Candidato: `nalgebra` con `LU` denso, factible para paneles ~hasta
  algunos miles antes de que O(n^3) empiece a doler.

## Primer caso candidato para arrancar
Electrostatica 2D: potencial y campo alrededor de uno o mas conductores con
potencial fijo (ecuacion de Laplace, sin fuente en el volumen -- BEM brilla
justo en este caso, exterior sin fuentes). Ejemplo de validacion: conductor
cilindrico con potencial V0 -- solucion analitica conocida en coordenadas
polares (phi = V0 * ln(r/r_ext)/ln(r_int/r_ext) para un capacitor cilindrico),
mismo espiritu que el chequeo phi(x,y)=x que uso fem_poisson2d.

## Pendiente antes de escribir codigo
- Definir el contrato JSON (geometria de borde: lista de paneles/segmentos con
  normales, en vez de rectangulo+nx+ny)
- Elegir crate para cuadratura singular y solver denso
- Decidir si el output devuelve potencial+campo solo en los paneles, o si
  ademas evalua en una grilla interior/exterior para graficar con plot_tool
