# TCC Traffic CV

Sistema experimental de controle semafórico adaptativo baseado em visão computacional.

O projeto integra SUMO, Unity, YOLOv8 e SORT para avaliar uma abordagem de otimização de tráfego urbano em ambiente simulado. O SUMO gera a dinâmica do tráfego, a Unity renderiza a cena 3D, o YOLO detecta veículos nos frames da câmera virtual, o SORT rastreia os veículos e um controlador semafórico toma decisões com base na estimativa visual de filas.

A decisão de controle não usa sensores perfeitos do SUMO. Os dados internos do SUMO são usados para renderização, sincronização e avaliação posterior.

## Arquitetura

`SUMO -> Python/TraCI -> Unity/SUMO2Unity -> camera -> Python/YOLO+SORT -> controlador -> SUMO`

## Principais módulos

- `python/sumo`: integração TraCI e extração de estado.
- `python/bridge`: comunicação Python e Unity.
- `python/vision`: detecção, rastreamento, ROI e estimativa de fila.
- `python/controller`: política de controle semafórico.
- `python/logging_utils`: logs, métricas e metadados de execução.
- `python/experiments`: execução de cenários e experimentos.
