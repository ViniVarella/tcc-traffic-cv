# Estatísticas do artigo (10 seeds, 201–210, percepção ground truth)

Média [IC 95%] por controlador; teste t pareado do modelo global contra cada um (diferença negativa = modelo global espera menos).

## SP `calibrated`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 12,9 ± 0,3 | 22,9 ± 0,5 | 0,2 ± 0,1 |
| Regra de fila (v2.0) | 4,3 ± 0,2 | 7,6 ± 0,2 | 0,0 ± 0,0 |
| Especialista | 4,2 ± 0,1 | 7,9 ± 0,2 | 0,0 ± 0,0 |
| Max-pressure | 5,0 ± 0,2 | 8,1 ± 0,2 | 0,0 ± 0,0 |
| Modelo global | 4,4 ± 0,1 | 7,7 ± 0,1 | 0,0 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -8,54 [-8,80; -8,27] | < 0,001 | -15,24 [-15,72; -14,77] | < 0,001 | 10/10 |
| Max-pressure | -0,60 [-0,88; -0,32] | < 0,001 | -0,47 [-0,69; -0,25] | < 0,001 | 9/10 |
| Especialista | 0,21 [0,04; 0,38] | 0,023 | -0,19 [-0,39; 0,02] | 0,076 | 2/10 |
| Regra de fila (v2.0) | 0,12 [-0,15; 0,40] | 0,330 | 0,03 [-0,16; 0,22] | 0,746 | 3/10 |

## SP `calibrated_ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 20,7 ± 0,5 | 33,9 ± 0,5 | 0,8 ± 0,1 |
| Regra de fila (v2.0) | 25,1 ± 1,5 | 29,2 ± 1,6 | 10,0 ± 5,3 |
| Especialista | 14,1 ± 0,3 | 18,2 ± 0,3 | 0,1 ± 0,0 |
| Max-pressure | 26,5 ± 1,2 | 29,7 ± 1,1 | 12,4 ± 4,8 |
| Modelo global | 14,7 ± 0,4 | 18,9 ± 0,4 | 0,1 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -5,93 [-6,68; -5,18] | < 0,001 | -15,00 [-15,73; -14,27] | < 0,001 | 10/10 |
| Max-pressure | -11,75 [-12,69; -10,82] | < 0,001 | -10,82 [-11,74; -9,90] | < 0,001 | 10/10 |
| Especialista | 0,66 [0,34; 0,99] | 0,001 | 0,72 [0,34; 1,09] | 0,002 | 1/10 |
| Regra de fila (v2.0) | -10,40 [-11,65; -9,15] | < 0,001 | -10,33 [-11,71; -8,94] | < 0,001 | 10/10 |

## SP `original`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 14,9 ± 0,1 | 22,7 ± 0,1 | 19,1 ± 1,2 |
| Regra de fila (v2.0) | 4,7 ± 0,1 | 7,4 ± 0,1 | 0,5 ± 0,0 |
| Especialista | 4,5 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |
| Max-pressure | 4,6 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |
| Modelo global | 4,7 ± 0,1 | 7,4 ± 0,1 | 0,5 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -10,28 [-10,41; -10,15] | < 0,001 | -15,39 [-15,55; -15,22] | < 0,001 | 10/10 |
| Max-pressure | 0,04 [-0,09; 0,17] | 0,538 | 0,03 [-0,09; 0,15] | 0,575 | 5/10 |
| Especialista | 0,16 [0,03; 0,30] | 0,023 | 0,09 [-0,05; 0,23] | 0,183 | 2/10 |
| Regra de fila (v2.0) | 0,00 [-0,15; 0,16] | 0,991 | -0,01 [-0,17; 0,15] | 0,902 | 5/10 |

## `cruz-assimetrico/baixa`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 21,7 ± 1,2 | 31,4 ± 1,1 | 0,0 ± 0,0 |
| Max-pressure | 9,9 ± 0,5 | 15,1 ± 0,7 | 0,0 ± 0,0 |
| Modelo global | 7,9 ± 0,5 | 12,5 ± 0,6 | 0,0 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -13,81 [-15,11; -12,50] | < 0,001 | -18,93 [-20,13; -17,73] | < 0,001 | 10/10 |
| Max-pressure | -2,03 [-2,91; -1,15] | < 0,001 | -2,61 [-3,71; -1,51] | < 0,001 | 9/10 |

## `cruz-assimetrico/baixa+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 38,8 ± 0,9 | 47,7 ± 0,8 | 0,0 ± 0,0 |
| Max-pressure | 20,9 ± 1,1 | 26,1 ± 1,3 | 0,0 ± 0,0 |
| Modelo global | 17,6 ± 1,5 | 22,5 ± 1,6 | 0,0 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -21,19 [-22,46; -19,93] | < 0,001 | -25,19 [-26,52; -23,86] | < 0,001 | 10/10 |
| Max-pressure | -3,30 [-4,93; -1,66] | 0,001 | -3,59 [-5,35; -1,84] | 0,001 | 9/10 |

## `cruz-assimetrico/media`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 31,8 ± 0,8 | 38,5 ± 0,8 | 0,1 ± 0,2 |
| Max-pressure | 20,3 ± 1,0 | 25,2 ± 1,1 | 0,5 ± 0,8 |
| Modelo global | 19,1 ± 2,1 | 23,2 ± 2,2 | 0,0 ± 0,0 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -12,77 [-14,60; -10,93] | < 0,001 | -15,32 [-17,27; -13,37] | < 0,001 | 10/10 |
| Max-pressure | -1,20 [-3,10; 0,69] | 0,184 | -2,00 [-4,07; 0,08] | 0,058 | 7/10 |

## `cruz-assimetrico/media+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 60,0 ± 1,7 | 63,3 ± 1,4 | 30,1 ± 6,1 |
| Max-pressure | 39,1 ± 0,8 | 43,0 ± 1,0 | 40,7 ± 6,8 |
| Modelo global | 45,4 ± 1,5 | 48,4 ± 1,4 | 35,6 ± 8,7 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -14,61 [-16,83; -12,39] | < 0,001 | -14,89 [-17,07; -12,71] | < 0,001 | 10/10 |
| Max-pressure | 6,22 [4,72; 7,72] | < 0,001 | 5,40 [4,18; 6,62] | < 0,001 | 0/10 |

## `cruz-assimetrico/desbalanceada`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 33,7 ± 1,2 | 40,3 ± 1,0 | 25,2 ± 7,4 |
| Max-pressure | 19,9 ± 0,4 | 24,1 ± 0,5 | 31,5 ± 8,6 |
| Modelo global | 19,7 ± 0,7 | 23,9 ± 0,7 | 34,1 ± 9,8 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -14,04 [-15,34; -12,74] | < 0,001 | -16,40 [-17,50; -15,30] | < 0,001 | 10/10 |
| Max-pressure | -0,19 [-1,01; 0,63] | 0,611 | -0,22 [-1,15; 0,70] | 0,599 | 5/10 |

## `cruz-assimetrico/desbalanceada+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 58,7 ± 1,2 | 63,8 ± 1,4 | 94,6 ± 12,2 |
| Max-pressure | 36,8 ± 3,0 | 40,4 ± 3,0 | 91,3 ± 8,9 |
| Modelo global | 32,2 ± 1,3 | 36,4 ± 1,2 | 84,3 ± 10,8 |

| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |
|---|---|---|---|---|---|
| Tempo fixo | -26,52 [-28,36; -24,68] | < 0,001 | -27,36 [-29,09; -25,62] | < 0,001 | 10/10 |
| Max-pressure | -4,61 [-7,15; -2,06] | 0,003 | -4,04 [-6,52; -1,56] | 0,005 | 9/10 |

