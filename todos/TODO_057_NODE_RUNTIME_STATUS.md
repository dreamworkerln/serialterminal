# Полный текущий статус LoRa-Chatter для preflight прогонов

TODO-ID: TODO_057
Status: OPEN / external firmware implementation / hardware validation OPEN
Recorded: 2026-10-17

## Запрос оператора

Перед передачей файла runner должен узнать, готова ли нода к работе и что она
сейчас делает. Если такого запроса нет, пропустить именно эту проверку и оформить
задачу для прошивки. Этот TODO фиксирует внешнюю firmware-зависимость; firmware
repository из source-задачи SerialTerminal не изменяется. Реализация требует
отдельной задачи оператора в firmware workspace.

## Текущее поведение и граница доказательств

Read-only inspection firmware repository `dreamworkerln/lora-sack-protocol`:

- `chatter/CHATTER_MACHINE_PROTOCOL_V1.md`, Types: M1 STATUS возвращает credits,
  drop/corrupt counters и high-water интерфейса. Он не содержит radio readiness,
  текущую работу scheduler или общую занятость ноды.
- `chatter/src/TerminalMachine.cpp`, `TerminalIo::machineStatus`: эти поля формируются
  без полного radio/scheduler snapshot. Полный credit не доказывает готовность RF.
- `chatter/src/TerminalIo.cpp`, `printHelp` и dispatcher: отдельного полного запроса
  runtime node status в исследованном source contract нет.
- `chatter/src/Scheduler.cpp`: setters отвергаются при активной radio/protocol
  transaction; `/config` сообщает настройки и часть link state.
- `/radio read config` и `/radio validate config` подтверждают регистры/соответствие
  радио конфигурации и ожидаемому RX mode; это не полный статус текущей работы.

Физическая версия firmware и наличие команды на подключённых нодах в этой задаче
не проверялись. Текущий runner явно пишет `node_status.outcome=SKIPPED` и причину
в `radio_preflight.json`; он не посылает выдуманный `/status` и не считает host
`status` или M1 credits полным ответом ноды.

## Требуемый результат отдельной firmware-задачи

- [ ] Согласовать и описать read-only запрос текущего состояния ноды.
- [ ] Ответ позволяет различить готовность/неисправность radio и текущую активность:
  idle, RX/TX, ожидание ACK/retry/backoff, USER/control очереди, recovery, diagnostic
  или другую работу. Уточнить перечень по реальным владельцам scheduler.
- [ ] Указать занятость и причину невозможности начать новую операцию; не подменять
  это одним интерфейсным credit либо наличием открытого USB/BLE соединения.
- [ ] Snapshot имеет определённые freshness/correlation semantics, ограниченный
  размер и не меняет RF/config/queues, не создаёт LoRa USER traffic.
- [ ] Определить поведение during startup, busy, degraded/recovery и при смене epoch.
- [ ] После принятия firmware contract подключить реальный запрос к runner и убрать
  SKIPPED только для подтверждённой реализации; неизвестный/потерянный ответ не
  трактовать как READY.

## Validation gates

- [ ] Firmware software tests для idle, каждой существенной busy/recovery/error
  ветки, а также отсутствия побочных действий запроса.
- [ ] Реальный hardware-прогон на обеих нодах по USB и BLE с подтверждённой версией
  firmware и source/runtime checkpoint, сохранёнными logs и отчётом в
  `journal_of_experiments/<UTC>_<сценарий>/`.
- [ ] Runner regression tests: READY допускает старт; BUSY/ERROR/unknown/silence
  дают диагностический отчёт и не запускают передачу.

TODO не закрыт. Текущий SF/BW/power/freq preflight и зелёные host tests не заменяют
реализацию и hardware validation полного node-status запроса.
