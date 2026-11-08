# Estatísticas do artigo (10 seeds, 201–210, percepção ground truth)

Média [IC 95%] por controlador; teste t pareado do TraffIQ v6.0 contra cada um (diferença negativa = v6.0 espera menos).

## SP `calibrated`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 12,9 ± 0,3 | 22,9 ± 0,5 | 0,2 ± 0,1 |
| Regra de fila (v2.0) | 4,3 ± 0,2 | 7,6 ± 0,2 | 0,0 ± 0,0 |
| TraffIQ v5.0 | 4,2 ± 0,1 | 7,9 ± 0,2 | 0,0 ± 0,0 |
| Max-pressure | 5,0 ± 0,2 | 8,1 ± 0,2 | 0,0 ± 0,0 |
| TraffIQ v6.0 | 4,0 ± 0,1 | 8,0 ± 0,2 | 0,0 ± 0,0 |
| v6.0 sem pedestres no treino | 4,0 ± 0,2 | 7,9 ± 0,2 | 0,0 ± 0,0 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -8,92 [-9,23; -8,60] | < 0,001 | -14,96 [-15,48; -14,43] | < 0,001 | 10/10 |
| Max-pressure | -0,98 [-1,28; -0,69] | < 0,001 | -0,18 [-0,44; 0,07] | 0,140 | 10/10 |
| TraffIQ v5.0 | -0,17 [-0,34; 0,00] | 0,056 | 0,10 [-0,13; 0,33] | 0,353 | 8/10 |
| Regra de fila (v2.0) | -0,25 [-0,53; 0,02] | 0,066 | 0,31 [0,17; 0,46] | < 0,001 | 7/10 |
| v6.0 sem pedestres no treino | 0,04 [-0,14; 0,22] | 0,631 | 0,11 [-0,15; 0,36] | 0,375 | 3/10 |

## SP `calibrated_ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 20,7 ± 0,5 | 33,9 ± 0,5 | 0,8 ± 0,1 |
| Regra de fila (v2.0) | 25,1 ± 1,5 | 29,2 ± 1,6 | 10,0 ± 5,3 |
| TraffIQ v5.0 | 14,1 ± 0,3 | 18,2 ± 0,3 | 0,1 ± 0,0 |
| Max-pressure | 26,5 ± 1,2 | 29,7 ± 1,1 | 12,4 ± 4,8 |
| TraffIQ v6.0 | 13,1 ± 0,4 | 18,6 ± 0,3 | 0,0 ± 0,0 |
| v6.0 sem pedestres no treino | 16,7 ± 1,6 | 21,2 ± 1,5 | 0,8 ± 0,7 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -7,58 [-8,09; -7,08] | < 0,001 | -15,37 [-15,96; -14,77] | < 0,001 | 10/10 |
| Max-pressure | -13,41 [-14,36; -12,46] | < 0,001 | -11,19 [-12,22; -10,17] | < 0,001 | 10/10 |
| TraffIQ v5.0 | -0,99 [-1,45; -0,54] | < 0,001 | 0,35 [-0,01; 0,71] | 0,056 | 10/10 |
| Regra de fila (v2.0) | -12,05 [-13,28; -10,82] | < 0,001 | -10,70 [-12,16; -9,23] | < 0,001 | 10/10 |
| v6.0 sem pedestres no treino | -3,65 [-5,10; -2,19] | < 0,001 | -2,69 [-4,16; -1,23] | 0,002 | 10/10 |

## SP `original`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 14,9 ± 0,1 | 22,7 ± 0,1 | 19,1 ± 1,2 |
| Regra de fila (v2.0) | 4,7 ± 0,1 | 7,4 ± 0,1 | 0,5 ± 0,0 |
| TraffIQ v5.0 | 4,5 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |
| Max-pressure | 4,6 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |
| TraffIQ v6.0 | 4,5 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |
| v6.0 sem pedestres no treino | 4,6 ± 0,1 | 7,3 ± 0,1 | 0,5 ± 0,0 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -10,40 [-10,54; -10,25] | < 0,001 | -15,46 [-15,62; -15,30] | < 0,001 | 10/10 |
| Max-pressure | -0,08 [-0,17; 0,01] | 0,069 | -0,04 [-0,14; 0,05] | 0,296 | 7/10 |
| TraffIQ v5.0 | 0,04 [-0,03; 0,12] | 0,220 | 0,02 [-0,06; 0,10] | 0,664 | 3/10 |
| Regra de fila (v2.0) | -0,12 [-0,25; 0,01] | 0,069 | -0,08 [-0,22; 0,05] | 0,182 | 7/10 |
| v6.0 sem pedestres no treino | -0,02 [-0,08; 0,04] | 0,504 | -0,01 [-0,05; 0,03] | 0,695 | 3/10 |

## `cruz-assimetrico/baixa`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 21,7 ± 1,2 | 31,4 ± 1,1 | 0,0 ± 0,0 |
| Max-pressure | 9,9 ± 0,5 | 15,1 ± 0,7 | 0,0 ± 0,0 |
| TraffIQ v6.0 | 7,7 ± 0,2 | 12,6 ± 0,4 | 0,0 ± 0,0 |
| v6.0 sem pedestres no treino | 6,4 ± 0,3 | 10,8 ± 0,4 | 0,0 ± 0,0 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -14,00 [-15,27; -12,74] | < 0,001 | -18,81 [-19,95; -17,67] | < 0,001 | 10/10 |
| Max-pressure | -2,23 [-2,77; -1,69] | < 0,001 | -2,48 [-3,47; -1,49] | < 0,001 | 10/10 |
| v6.0 sem pedestres no treino | 1,29 [0,97; 1,60] | < 0,001 | 1,73 [1,18; 2,28] | < 0,001 | 0/10 |

## `cruz-assimetrico/baixa+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 30,6 ± 0,8 | 40,1 ± 0,5 | 0,0 ± 0,0 |
| Max-pressure | 12,7 ± 1,0 | 18,3 ± 1,0 | 0,0 ± 0,0 |
| TraffIQ v6.0 | 7,0 ± 0,4 | 11,6 ± 0,5 | 0,0 ± 0,0 |
| v6.0 sem pedestres no treino | 8,3 ± 0,6 | 13,1 ± 0,7 | 0,0 ± 0,0 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -23,65 [-24,45; -22,85] | < 0,001 | -28,46 [-29,29; -27,62] | < 0,001 | 10/10 |
| Max-pressure | -5,70 [-6,47; -4,94] | < 0,001 | -6,65 [-7,50; -5,79] | < 0,001 | 10/10 |
| v6.0 sem pedestres no treino | -1,29 [-1,96; -0,63] | 0,002 | -1,44 [-2,12; -0,76] | < 0,001 | 9/10 |

## `cruz-assimetrico/media`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 31,8 ± 0,8 | 38,5 ± 0,8 | 0,1 ± 0,2 |
| Max-pressure | 20,3 ± 1,0 | 25,2 ± 1,1 | 0,5 ± 0,8 |
| TraffIQ v6.0 | 16,8 ± 2,6 | 21,0 ± 2,6 | 0,0 ± 0,0 |
| v6.0 sem pedestres no treino | 15,6 ± 1,0 | 19,4 ± 1,0 | 0,0 ± 0,0 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -15,05 [-17,80; -12,29] | < 0,001 | -17,53 [-20,31; -14,75] | < 0,001 | 10/10 |
| Max-pressure | -3,48 [-5,90; -1,07] | 0,010 | -4,20 [-6,73; -1,68] | 0,004 | 9/10 |
| v6.0 sem pedestres no treino | 1,21 [-1,52; 3,94] | 0,342 | 1,53 [-1,24; 4,31] | 0,243 | 7/10 |

## `cruz-assimetrico/media+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 50,4 ± 2,5 | 55,4 ± 2,1 | 7,7 ± 4,9 |
| Max-pressure | 25,4 ± 0,9 | 30,4 ± 0,9 | 2,0 ± 1,6 |
| TraffIQ v6.0 | 21,3 ± 2,4 | 26,0 ± 2,5 | 0,1 ± 0,1 |
| v6.0 sem pedestres no treino | 23,2 ± 2,8 | 27,4 ± 2,6 | 1,3 ± 1,9 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -29,18 [-31,41; -26,95] | < 0,001 | -29,33 [-31,59; -27,07] | < 0,001 | 10/10 |
| Max-pressure | -4,10 [-6,87; -1,34] | 0,008 | -4,36 [-7,18; -1,55] | 0,007 | 8/10 |
| v6.0 sem pedestres no treino | -1,98 [-4,94; 0,98] | 0,165 | -1,42 [-4,35; 1,51] | 0,301 | 7/10 |

## `cruz-assimetrico/desbalanceada`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 33,7 ± 1,2 | 40,3 ± 1,0 | 25,2 ± 7,4 |
| Max-pressure | 19,9 ± 0,4 | 24,1 ± 0,5 | 31,5 ± 8,6 |
| TraffIQ v6.0 | 20,4 ± 1,7 | 24,6 ± 1,6 | 11,5 ± 6,3 |
| v6.0 sem pedestres no treino | 19,6 ± 0,7 | 24,7 ± 0,9 | 17,6 ± 7,3 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -13,31 [-15,21; -11,42] | < 0,001 | -15,69 [-17,43; -13,96] | < 0,001 | 10/10 |
| Max-pressure | 0,54 [-1,26; 2,34] | 0,515 | 0,48 [-1,33; 2,29] | 0,563 | 3/10 |
| v6.0 sem pedestres no treino | 0,85 [-0,63; 2,33] | 0,226 | -0,09 [-1,48; 1,31] | 0,891 | 4/10 |

## `cruz-assimetrico/desbalanceada+ped`

| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |
|---|---|---|---|
| Tempo fixo | 55,8 ± 2,8 | 61,6 ± 2,7 | 52,0 ± 8,8 |
| Max-pressure | 21,1 ± 0,6 | 25,2 ± 0,9 | 43,6 ± 10,8 |
| TraffIQ v6.0 | 21,0 ± 1,4 | 25,6 ± 1,3 | 19,6 ± 8,3 |
| v6.0 sem pedestres no treino | 21,9 ± 0,8 | 26,8 ± 0,9 | 35,0 ± 10,2 |

| v6.0 contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que a v6.0 vence |
|---|---|---|---|---|---|
| Tempo fixo | -34,78 [-38,23; -31,34] | < 0,001 | -35,99 [-39,25; -32,73] | < 0,001 | 10/10 |
| Max-pressure | -0,06 [-1,79; 1,67] | 0,936 | 0,35 [-1,46; 2,17] | 0,669 | 6/10 |
| v6.0 sem pedestres no treino | -0,88 [-2,57; 0,81] | 0,269 | -1,19 [-2,79; 0,42] | 0,128 | 6/10 |

