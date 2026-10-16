# TUI file transfer: progress window and explicit cancellation TODO

TODO-ID: TODO_052
Status: OPEN
Recorded: 2026-10-16

## Purpose

Сделать нормальный интерфейс передачи файла по образцу Midnight Commander:
отдельное устойчивое окно прогресса, понятные показатели и явное управление.
Переключение отображения телеметрии и обычный Enter не должны отменять файл.

Оператор подтвердил 2026-10-16: `/tele` — включение отображения телеметрии,
а не команда отмены; желаемый ориентир интерфейса — Midnight Commander.
Уточнения оператора: дизайн «Передача файла» принят; окно по центру TUI,
широкое, близкое к ширине терминала, без кнопки отмены. Окно и confirmation
нормально перестраиваются при terminal resize; длинное имя не ломает layout.
Esc открывает отдельный TUI dialog «Отменить передачу файла?».
Финальный порядок вариантов, слева направо: «Нет», «Да»; по умолчанию выбрано
«Да». ←/→ меняют выбор, Enter подтверждает; повторный Esc продолжает передачу.
Слишком длинное для протокола имя: сообщение в консоль «Имя файла слишком
длинное» и отказ до начала передачи, без обрезания или переименования.

## Finding checkpoint and current behavior

Source checkpoint: `dev_tui_exp_recursive_missing`, HEAD
`ee9e954339f37a541f303aeec98d560b09794758` + существующие local changes.
Это checkpoint исследования, а не версия с реализованным новым интерфейсом.

В `src/serialterminal/tui_core.py`:

* `_submit_input()` безусловно вызывает `_abort_and_reconnect_same_target()`
  перед обработкой любого ввода — даже `/tele` или пустого Enter.
* Активная FT1 отменяется, `_replace_tui_session()` закрывает старый manager
  и создаёт новый. Старый progress snapshot теряется, поэтому верхний
  прогрессбар исчезает. Это lifecycle-эффект, а не просто визуальная прокрутка.
* `_abort_file_transfer_for_operator()` снимает screen mute. Служебные пустые
  строки от machine frames становятся видны и быстро заполняют scrollback.
* Progress пока рисуется двумя строками над scrollback, без отдельного окна
  управления и явного focus contract.

Подтверждающие сохранённые данные оператора в `bad_logs/`:

* `serialterminal-application-20261016-014240-711352-p616264.log`:
  02:02:31.574 — manual input, explicit cancel `db533e0f3d59372f`, session
  replacement и manager close; в соответствующем `.console.log` в
  02:02:31.800 записан `/tele`.
* `serialterminal-20261016-014245-062041-p616239.console.log` содержит 4956
  пустых RX lines и 4956 `/m1` lines; соседний receiver log — 4911 пустых lines.
* Два поздних application logs, `020337-523196-p619638` и
  `020339-833953-p619643`, содержат traceback `ValueError: embedded null character`
  из curses `addnstr`; в каждом соответствующем console log есть 343 NUL.
  NUL bursts предшествуют firmware boot messages; причина этих входящих bytes
  отдельно не установлена, повреждение файла ими не доказано.

Отдельный текущий bugfix в working tree убирает пустые Chatter delimiters из
human screen и экранирует C0/C1 перед TUI wrap/draw. Он не реализует это TODO:
правило отмены на Enter и старый progress UI пока остаются.

## Target behavior

1. Широкое окно «Передача файла» по центру TUI, по образцу Midnight Commander,
   близкое к доступной ширине терминала с небольшими боковыми полями.
   Не ограничивать его фиксированной узкой шириной при широком terminal.
   В окне: имя файла, направление TX/RX, понятное состояние/стадия, прогресс,
   обработанные/всего bytes, скорость, elapsed и ETA, если их можно достоверно
   рассчитать. Неизвестные значения показывать явно, без выдуманного ETA/процента.
   В окне прогресса нет кнопки «Отмена».
   При каждом resize пересчитывать размер, центрирование, переносы имени и ширину
   progress bar; confirmation dialog также остаётся внутри доступной области.
   При уменьшении окна не терять transfer_id, фокус, выбранный ответ или progress.
   При недостаточном размере использовать компактное представление/сообщение
   о размере терминала, сохраняя FT1 и восстанавливая окно после расширения.
   Длинное имя переносить по доступной ширине, учитывая ширину Unicode в ячейках
   terminal. При нехватке высоты ограничивать строки и показывать многоточие,
   сохраняя узнаваемые начало и конец с расширением; полный basename остаётся
   доступен в деталях. Сокращается только экранное представление, не передаваемое имя.
2. Esc при активном окне передачи открывает поверх него TUI dialog box
   «Отменить передачу файла?» с вариантами «Нет» слева и «Да» справа.
   ←/→ меняют выбор, Enter подтверждает выбранный вариант.
   По умолчанию выбрано «Да», как явно указал оператор.
   «Нет» или повторный Esc закрывают только confirmation dialog и возвращают
   окно прогресса. Только «Да» + Enter запускает FT1 cancellation.
   Все окна и элементы выбора рисуются внутри curses/TUI, без GUI dialogs.
   Пока оператор выбирает ответ, передача продолжается; её worker не блокируется.
   Диалог привязан к конкретному transfer_id: если операция успела завершиться,
   запоздалый ответ не отменяет другую или новую передачу.
   Управление «Свернуть/В фон» и возврат имеют отдельные явные focus/keyboard
   semantics и сохраняют ту же операцию, transfer_id, стадию и актуальный прогресс.
   Esc не совмещать со сворачиванием: его действие здесь — запрос подтверждения.
3. В командной строке Enter только отправляет введённую команду. Пустой Enter
   не отменяет передачу и не пересоздаёт session/manager/adapter.
   Enter вне confirmation dialog не должен по неявному default focus запускать
   отмену. Открытый dialog получает ←/→/Enter/Esc локально, без передачи этих
   клавиш в command input или контроллер.
4. `/tele`, `/chat`, `/both` и соответствующие profile hotkeys меняют human
   output mode без отмены, скрытого reconnect, сброса прогресса, нового META
   или смены transfer_id. Диагностика становится видна по выбранному режиму,
   а machine/base64 delimiters не засоряют экран.
5. FT1 cancellation из progress UI запускается только после подтверждения
   «Да» + Enter. Если F6 сохраняется как shortcut, он открывает тот же dialog,
   а не обходит подтверждение. Ctrl+C/Ctrl+Q сохраняют обычный process exit.
   Семантику typed controller `/cancel` не смешивать молча с локальным FT1 cancel.
6. Локальные UI-действия (scroll/history/help/clear/resize) не меняют lifecycle
   передачи. Терминальный результат — completed/failed/cancelled с причиной —
   остаётся доступен; прогресс не исчезает без объяснения.
7. ROOT file progress отделён от текущей стадии recursive multi missing:
   служебный missing-list файл не должен подменять имя и прогресс ROOT.
   DATA stream, repair, ожидание RESULT и завершение различимы. Процент
   serviced DATA не означает remote durability или успешную передачу;
   успех устанавливается только по FT1 RESULT contract.

## Filename transport and early rejection

Текущий FT1 v3 передаёт basename (без локального пути) целиком в UTF-8 внутри
одного META. `filename_len` — число bytes, не Unicode characters. При Chatter
`payload_capacity=243` общий header занимает 12 bytes, фиксированная META — 69,
поэтому на имя с расширением остаётся 162 UTF-8 bytes. Поле uint8 само по себе
не означает поддержку имени длиной 255 bytes: раньше достигается предел пакета.
Источник: `file_transfer/protocol.py:encode_meta`, `resume_source.py:prepare_source`,
[FILE_TRANSFER.md, META](../FILE_TRANSFER.md#10-meta).

Проверено 2026-10-16: ASCII162 и 81 букв «я» кодируются в META размером 243 bytes
и round-trip сохраняет имя; ASCII163/255 и 82/255 букв «я» отклоняются с
`META filename does not fit one binary USER`. Существующий targeted test
`test_v3_meta_filename_budget_matches_extended_fixed_header` — 1 PASS.
Это codec/subset validation, без физических устройств. Текущий send worker
подготавливает источник до кодирования META; раннего понятного UI отказа ещё нет.

Согласованное поведение для этого TODO:

* До начала FT1 проверить размер basename в UTF-8 против фактического бюджета
  metadata выбранного binary transport. Бюджет/валидация принадлежат FT1;
  TUI не дублирует magic number 162 и не знает Chatter wire layout.
* При превышении вывести в консоль «Имя файла слишком длинное»; можно дополнить
  фактическим размером и разрешённым числом bytes. Не начинать передачу:
  без подготовки/compression файла, claim FT1, нового sender journal или META/DATA.
  Не показывать фиктивное «передача начата» и не отменять другую активную операцию.
* Не обрезать и не переименовывать файл автоматически. Long-name display
  и ограничение wire budget — разные условия, оба должны быть объяснимы в UI.
* Для действующего Chatter имя из 255 ASCII-символов или 255 русских букв
  не передаётся. Поддержка имён сверх бюджета одного META требует отдельного
  решения FT1 metadata protocol; этот UI TODO wire format не расширяет.

## Scope and invariants

* Human TUI, profile-owned action classification, progress/focus/lifecycle
  presentation, regression tests и согласованная документация.
* Generic TUI использует profile capability для семантики команд. Не помещать
  проверки конкретных `/tele`/Chatter aliases в generic session/transport.
* Сохранить ordered TX, существующую machine correlation/ownership и FT1
  recovery/resume. Отображение и telemetry не становятся control plane.
* Команды, меняющие PHY, reboot/device/profile, и обычный radio USER input
  требуют явной отдельной политики допуска при занятой FT1. Нельзя считать
  любой текст неявным cancel и нельзя обходить ownership, слепо пропуская всё.
  Конкретную классификацию обосновать и согласовать при реализации.
* Не менять firmware, wire format или recursive multi missing ради UI.
* ROOT/repair presentation должна отражать существующие snapshots/events,
  а не вводить второй независимый учёт FT1 data.
* Связанные TODO: TODO_014 (canonical human line assembly), TODO_039
  (TUI menu), TODO_042 (recursive missing), TODO_051 (общий CI plan).
  Это TODO не переоткрывает и не подменяет их scope.

## Implementation

- [ ] Убрать безусловную отмену из `_submit_input()`; определить безопасный
      profile-owned admission для действий при активной TX/RX.
- [ ] Провести `/tele`, `/chat`, `/both` и hotkeys без preemption/reconnect.
- [ ] Сделать широкое окно «Передача файла» по центру TUI по образцу MC
      без кнопки отмены, с понятным focus и отдельным возвратом из фона.
- [ ] Перестраивать progress/confirmation при terminal resize; обработать
      длинные имена, Unicode cell widths, недостаточные ширину/высоту без
      потери FT1 state. Поддержать просмотр полного basename.
- [ ] Выполнить общий FT1 preflight длины имени в UTF-8 до начала передачи;
      при превышении бюджета вывести «Имя файла слишком длинное» в консоль
      и не начинать FT1/preparation/journal; без silent truncation/rename.
- [ ] Реализовать Esc → TUI confirmation «Отменить передачу файла?» →
      «Нет» слева / «Да» справа, ←/→ и Enter; default «Да», повторный Esc
      возвращает к progress.
      Привязать dialog к transfer_id, не блокировать передачу при выборе ответа.
- [ ] Исключить случайный cancel по Enter в command input; F6, если сохранён,
      должен использовать тот же confirmation path.
- [ ] Сохранить identity/snapshot активной операции при UI actions; показать
      ROOT и текущую recursive repair стадию без потери общей картины.
- [ ] Сохранить доступный terminal outcome и причину завершения.
- [ ] Проверить screen-noise/telemetry policy: после `/tele` полезная telemetry
      видна, machine delimiters скрыты, progress area не вытесняется scrollback.
- [ ] Обновить ARCHITECTURE.md (сейчас manual input описан как preemption),
      README, help, AGENT_API.md и runtime skill по применимости.

## Validation and acceptance

- [ ] Для TX и RX: Enter с `/tele`, `/chat`, `/both`, hotkeys и пустой Enter
      не вызывают manager.cancel/close, transport reconnect, session replacement
      или новый transfer_id. Передача продолжает двигаться к RESULT.
- [ ] TUI integration test: активный файл → открыть/свернуть progress window →
      `/tele` → интенсивный output → вернуться; видны тот же ROOT, actual progress
      и состояние, полезная telemetry отображается.
- [ ] Esc открывает confirmation dialog без отмены/паузы FT1:
      «Нет» слева, «Да» справа, изначально выбрано «Да».
      ←/→ меняют только выбор в dialog, Enter на «Нет» и повторный Esc возвращают
      progress, Enter на «Да» отменяет именно привязанный transfer_id.
- [ ] Если F6 сохранён, он открывает тот же dialog. Enter вне confirmation,
      сворачивание, scroll, clear/help и resize не запускают cancellation.
- [ ] Передача, завершившаяся при открытом confirmation, показывает terminal
      outcome; запоздалый «Да» не отменяет новый transfer. Клавиши modal dialog
      не утекают в command input/transport TX.
- [ ] Проверить terminal widths 60/80/120/200 и уменьшение/расширение при
      открытом progress и confirmation; окно использует доступную ширину,
      не выходит за границы, сохраняет focus/selection/transfer_id и progress.
- [ ] Длинные ASCII/Cyrillic имена, emoji/combining/wide characters: корректные
      переносы/ellipsis/полное имя, без порчи рамки и progress; расширение окна
      возвращает доступный текст. Проверить имена до 255 characters на display
      отдельно от возможности передать их текущим protocol.
- [ ] Для Chatter preflight: 162 ASCII bytes и 81 букв «я» проходят, 163/255
      ASCII bytes и 82/255 букв «я» отклоняются до подготовки, journal и META.
      Включить extension и другие transport capacities; assert console message
      «Имя файла слишком длинное» и отсутствие start/claim/send side effects.
- [ ] Минимальные/недостаточные размеры terminal, follow/scrollback и focus
      между command input и progress controls не приводят к cancellation.
- [ ] ROOT + recursive missing-list/repair, ожидание RESULT, local reconnect,
      completed/failed/cancelled, включая открытый confirmation dialog:
      UI показывает правдивую стадию и outcome,
      скорость/ETA не становятся отрицательными или фиктивными.
- [ ] Воспроизвести сохранённый blank/NUL output в псевдотерминале: окно/панель
      не повреждается, curses не падает, исходные evidence logs не меняются.
- [ ] Новые regression tests входят в общий pytest/CI plan; выполнить полный
      software suite по правилам TODO_051 без ослабления обязательных checks.
- [ ] Отдельно по разрешению оператора выполнить ручной TUI smoke на двух
      нодах: реальная передача, `/tele`, возврат к progress, RESULT и cancel.
      Сохранить exact source checkpoint, logs и фактический PASS/FAIL.

## Separate display-safety fix validation — 2026-10-16

Это проверка сопутствующего исправления blank/NUL output, а не приёмка TODO_052.
На указанном HEAD с local changes: `pytest -q` — 917 PASS / 95.99 s;
regression subset — 72 PASS; `python -m compileall -q src serialterminal.py tools`
— PASS. Ruff не выполнен: executable отсутствует в окружении.
Четыре сохранённых console logs отрисованы настоящим curses в локальном PTY:
PASS, контрольная верхняя строка сохранена, 686 NUL отображены escapes.
Физические порты/ноды не использовались; источник входящих NUL не установлен.

Проверенные Git blob hashes display source files (не commit):

* `src/serialterminal/tui_core.py`: `5e4997d13168b03afa6d4674e152b0751f2d3438`.
* `src/serialterminal/profiles/chatter/profile.py`: `1c613dd314fc093fd4b12958e003471eb1225b2f`.

## Result

Implemented: NO (progress/admission redesign).
Validated: source/log inspection only for this TODO; нового TUI ещё нет.
Status: OPEN. Hardware validation не выполнялась.
