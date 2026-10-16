# TUI file transfer: progress window and explicit cancellation TODO

TODO-ID: TODO_052
Status: IMPLEMENTED / hardware validation OPEN
Recorded: 2026-10-16

Current follow-up: [TODO_053_TUI_FILE_TRANSFER_WINDOW_LIFECYCLE.md](TODO_053_TUI_FILE_TRANSFER_WINDOW_LIFECYCLE.md)
supersedes the window lifecycle/background/cancel rules below with the operator's
latest contract. Previous implementation history and physical validation gates remain.

## Purpose

Сделать нормальный интерфейс передачи файла по образцу Midnight Commander:
отдельное устойчивое окно прогресса, понятные показатели и явное управление.
Формат вывода контроллера независим от FT1; обычный Enter не управляет передачей файла.

Оператор подтвердил 2026-10-16: `/tele`, `/chat`, `/both` — только переключение
формата вывода контроллера (telemetry / chat / оба). Это самостоятельная
presentation-функция: она не является командой FT1, не управляет его lifecycle
и не задаёт условия допуска/отмены/продолжения передачи. Желаемый ориентир
интерфейса передачи — Midnight Commander.
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
4. Переключение формата human output — независимая profile-owned функция.
   `/tele`, `/chat`, `/both` и соответствующие hotkeys меняют только состав
   вывода контроллера. FT1 не распознаёт эти команды и не принимает по ним
   решений: output mode не является его control plane или admission gate.
   Переключение не меняет session/manager, transfer_id, состояние или progress;
   не создаёт META, reconnect, cancel, pause/resume и не требует остановки файла.
   Пользователь видит выбранный формат; machine/base64 delimiters скрываются
   presentation layer независимо от активности FT1.
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
  recovery/resume. Формат human output и FT1 независимы: не вводить whitelist
  `/tele`/`/chat`/`/both` в file manager или исключения для них в FT1 ownership.
  Доставка profile presentation-команд не должна вызывать file preemption.
  Проверка этих команд во время передачи — regression на отсутствие связи,
  а не отдельный режим работы или специальное разрешение FT1.
* Команды, меняющие PHY, reboot/device/profile, и обычный radio USER input
  требуют явной отдельной политики допуска при занятой FT1. Нельзя считать
  любой текст неявным cancel и нельзя обходить ownership, слепо пропуская всё.
  Оператор согласовал 2026-10-16: отклонять такие действия до completion/cancel,
  не отменяя файл. Основное TUI остаётся доступным для viewing/presentation;
  только confirmation modal захватывает ввод.
* Не менять firmware, wire format или recursive multi missing ради UI.
* ROOT/repair presentation должна отражать существующие snapshots/events,
  а не вводить второй независимый учёт FT1 data.
* Связанные TODO: TODO_014 (canonical human line assembly), TODO_039
  (TUI menu), TODO_042 (recursive missing), TODO_051 (общий CI plan).
  Это TODO не переоткрывает и не подменяет их scope.

## Implementation

- [x] Убрать безусловную отмену из `_submit_input()`; определить безопасный
      profile-owned admission для действий при активной TX/RX.
- [x] Разделить profile presentation actions и управление FT1; переключение
      формата вывода работает независимо, без FT1-specific обработки команд,
      preemption, reconnect или требований к состоянию передачи.
- [x] Сделать широкое окно «Передача файла» по центру TUI по образцу MC
      без кнопки отмены, с понятным focus и отдельным возвратом из фона.
- [x] Перестраивать progress/confirmation при terminal resize; обработать
      длинные имена, Unicode cell widths, недостаточные ширину/высоту без
      потери FT1 state. Не изменять полный basename в snapshot/log; отображать переносы/ellipsis.
      По позднему решению оператора отдельный F10-view удалён без новой клавиши.
- [x] Выполнить общий FT1 preflight длины имени в UTF-8 до начала передачи;
      при превышении бюджета вывести «Имя файла слишком длинное» в консоль
      и не начинать FT1/preparation/journal; без silent truncation/rename.
- [x] Реализовать Esc → TUI confirmation «Отменить передачу файла?» →
      «Нет» слева / «Да» справа, ←/→ и Enter; default «Да», повторный Esc
      возвращает к progress.
      Привязать dialog к transfer_id, не блокировать передачу при выборе ответа.
- [x] Исключить случайный cancel по Enter в command input; F6, если сохранён,
      должен использовать тот же confirmation path.
- [x] Сохранить identity/snapshot активной операции при UI actions; показать
      ROOT и текущую recursive repair стадию без потери общей картины.
- [x] Сохранить доступный terminal outcome и причину завершения.
- [x] Проверить presentation policy независимо от FT1: выбранный формат
      вывода соблюдается, machine delimiters скрыты, интенсивный scrollback
      не вытесняет progress window и не управляет передачей.
- [x] Обновить ARCHITECTURE.md (сейчас manual input описан как preemption),
      README, help, AGENT_API.md и runtime skill по применимости.

## Validation and acceptance

- [x] Regression независимости output format от FT1: `/tele`, `/chat`, `/both`
      и hotkeys переключают формат при idle, TX и RX одинаково; FT1 не получает
      этих команд как file-control actions. Проверить отсутствие manager.cancel/
      close, pause/resume, reconnect, session replacement, нового transfer_id
      и повторного META; активный файл продолжает двигаться к RESULT.
- [x] Пустой Enter в command input не управляет передачей и не пересоздаёт
      session/manager/adapter.
- [x] TUI integration test: активный файл → открыть/свернуть progress window →
      `/tele` → интенсивный output → вернуться; видны тот же ROOT, actual progress
      и состояние, полезная telemetry отображается.
- [x] Esc открывает confirmation dialog без отмены/паузы FT1:
      «Нет» слева, «Да» справа, изначально выбрано «Да».
      ←/→ меняют только выбор в dialog, Enter на «Нет» и повторный Esc возвращают
      progress, Enter на «Да» отменяет именно привязанный transfer_id.
- [x] Если F6 сохранён, он открывает тот же dialog. Enter вне confirmation,
      сворачивание, scroll, clear/help и resize не запускают cancellation.
- [x] Передача, завершившаяся при открытом confirmation, показывает terminal
      outcome; запоздалый «Да» не отменяет новый transfer. Клавиши modal dialog
      не утекают в command input/transport TX.
- [x] Проверить terminal widths 60/80/120/200 и уменьшение/расширение при
      открытом progress и confirmation; окно использует доступную ширину,
      не выходит за границы, сохраняет focus/selection/transfer_id и progress.
- [x] Длинные ASCII/Cyrillic имена, emoji/combining/wide characters: корректные
      переносы/ellipsis/полное имя, без порчи рамки и progress; расширение окна
      возвращает доступный текст. Проверить имена до 255 characters на display
      отдельно от возможности передать их текущим protocol.
- [x] Для Chatter preflight: 162 ASCII bytes и 81 букв «я» проходят, 163/255
      ASCII bytes и 82/255 букв «я» отклоняются до подготовки, journal и META.
      Включить extension и другие transport capacities; assert console message
      «Имя файла слишком длинное» и отсутствие start/claim/send side effects.
- [x] Минимальные/недостаточные размеры terminal, follow/scrollback и focus
      между command input и progress controls не приводят к cancellation.
- [x] ROOT + recursive missing-list/repair, ожидание RESULT, local reconnect,
      completed/failed/cancelled, включая открытый confirmation dialog:
      UI показывает правдивую стадию и outcome,
      скорость/ETA не становятся отрицательными или фиктивными.
- [x] Воспроизвести сохранённый blank/NUL output в псевдотерминале: окно/панель
      не повреждается, curses не падает, исходные evidence logs не меняются.
- [x] Новые regression tests входят в общий `pytest -q`, который запускается
      также CI; pyte — обязательная dev dependency, PTY test не имеет skip.
- [ ] Общий full CI gate: блокирован тремя существовавшими F401 и открытым
      TODO_051 (единый executor/dependency parity). Полный pytest и compile
      проверены отдельно; не называть их full CI PASS.
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

## Implementation/software checkpoint — 2026-10-16

Base HEAD: `dev_tui_exp_recursive_missing@b0211ae6cb62dfafb0f0da8bb2d06457a4975fdb`
+ текущие uncommitted изменения. Это software checkpoint, не аппаратное evidence.

Runtime fingerprint (57 files: `pyproject.toml`, `serialterminal.py`, `src/**/*.py`):
`08d7808b28c96b89e4184ee823ab0dfe1024e6279270f8b71a39eafcec8799c8`.
Tests fingerprint (79 files: `tests/**/*.py`):
`d760f77a732e7d7c5e32197f1da31ab6c1b181c2034665010e52ffa789645c09`.
Алгоритм для обоих: SHA256 конкатенации `relative_path UTF-8 + NUL + bytes + NUL`
в лексикографическом порядке путей.

Реализация:

* `tui_file_transfer.py` — frontend-only окно/confirmation, F7/F10, paging basename,
  ROOT identity и outcome; без второго FT1 coordinator. При малом terminal
  невидимое подтверждение не принимается. ncurses layout использует libc widths,
  чтобы ZWJ emoji и разные Unicode tables не сдвигали рамку.
* Profile-owned `human_action_is_non_disruptive`: output controls и status queries
  доступны, mutations/RF text/device/profile отклоняются до освобождения ownership.
  Основное окно не блокируется; Enter никогда не является неявной отменой.
* `_cancel_confirmed_file` адресует ID, не reconnect/close. Snapshot/manager/session
  не заменяются при output selection. Machine/BINARY presentation фильтруется
  профилем одинаково при idle/active FT1; blanket FT1 screen mute удалён.
* Общий filename preflight использует codec budget до resume lookup/reservation/
  claim/preparation. Проверен exact boundary send через настоящий FT1 coordinator
  с парными in-memory transports, без аппаратуры. Ошибка выводится в console.
* `elapsed` растёт в активной runtime attempt и фиксируется при terminal.
  DATA ETA отсутствует на repair/RESULT; compression progress не назван wire rate.

Software validation (вне ограничивающего sandbox):

* Финальный полный `pytest -q`: **995 PASS / 98.48 s**, без skips.
* Targeted curses/window/browser — 72 PASS; filename/resume/chunk-space subset —
  49 PASS. Это subset validation, не отдельное аппаратное evidence.
* `python -m compileall -q src serialterminal.py usb_timing_logger.py tools scripts`
  — PASS. Ruff изменённых файлов — PASS; полный Ruff — FAIL: существовавшие
  `pipeline_manager.py` unused `.manager`, `recursive.py` unused `Path`,
  `tests/test_ft1_outbox.py` unused `time`. Все три воспроизведены на base HEAD;
  посторонняя чистка в задачу не включена. Advisory Lizard выполнен с warning exit,
  как и разрешает текущая CI nonblocking policy; это не blocking PASS.
* Настоящий curses в PTY: 10 000 строк flood с NUL/ESC/C1, blank/machine filtering,
  resize 60/80/120/200 и 35×8 → restore, default/order/keys confirmation,
  background/full-name/outcome, cursor focus и координаты Unicode рамки — PASS.
  Transport этого test падает при любом connect/read/write, поэтому железа нет.
* Все четыре сохранённых `bad_logs/*.console.log` повторно replay через настоящий
  curses с новым progress overlay: 50 кадров, 686 NUL, PASS. Исходные SHA256
  before/after совпали. Software evidence: `/tmp/st-todo052-replay/evidence.json`
  и `curses.ansi`; logs не изменены и не добавлены в Git.
* `AGENT_API.md` и runtime skill согласованы с новым filename/elapsed contract;
  agent session mutation ownership не ослаблен. Architecture dependency direction
  сохранён: Chatter command classification только в profile, не в FT1/transports.
  Observation hardware skill просмотрен: JSONL semantics не изменились,
  инфраструктурные правки в observation workspace не требуются.

## Selector redraw regression — 2026-10-16

После реализации оператор сообщил задержку 0.5–1 s на стрелках в FileBrowser.
Это подтверждённая host/UI regression: `fit_cells` для каждого cluster заново
вызывал `cell_width` на всём растущем prefix. В кадре 240×60 — 1,649,088 вызовов
libc width в regression fixture; profiling показывал основное время в этих
повторных измерениях. Содержимое выбранного файла при навигации не читалось.

Исправлены `fit_cells`, `wrap_cells` и `middle_ellipsis`: ширина накапливается
за один проход, строки собираются через join; printable ASCII имеет простой
путь без libc. Правила libc widths, clusters, controls и Unicode clipping сохранены.
Отрисовка — целая строка одним addnstr и один refresh на кадр. Механика
соответствует [Python curses HOWTO](https://docs.python.org/3/howto/curses.html#windows-and-pads)
и [ncurses refresh](https://invisible-island.net/ncurses/man/curs_refresh.3x.html):
curses собирает desired screen, затем оптимизирует обновление terminal.

Evidence:

* `test_arrow_navigation_redraw_has_linear_unicode_width_work` сначала **FAIL**
  на старом коде (1,649,088 calls > 115,200 budget), после исправления **PASS**.
  Проверяет настоящий FileBrowser.draw/handle_key ↑/↓, линейный бюджет работы,
  целые строки, единственный refresh, отсутствие повторного directory scan.
  Это deterministic resource test, без нестабильного wall-clock threshold.
* Три отдельные regression fit/wrap/ellipsis проверяют линейную работу с
  Cyrillic/wide/combining/ZWJ/flag text. Существующий настоящий curses/PTY test
  проверяет сохранение Unicode layout и координат рамки.
* Одинаковый offline render benchmark, 100 entries (с Cyrillic names):
  80×24 **33.9 → 3.0 ms**, 160×40 **237.2 → 9.4 ms**,
  240×60 **974.2 → 21.9 ms**, 320×80 **2353.3 → 42.6 ms**.
  Это стоимость подготовки кадра с fake screen, не end-to-end latency.
* Настоящий curses/PTY 240×60, реальные arrow escape sequences, два каталога
  по 100 пустых файлов: ↓ **28.8 ms**, → **32.2 ms**, ↓ **29.5 ms**,
  ↑ **28.8 ms**, ← **30.5 ms**. Порты/ноды не открывались.
  Проверочный скрипт `/tmp/st-browser-navigation-pty.py`.
* Финальный полный `pytest -q`: **999 PASS / 101.05 s**, без skips.
  Compile полного CI scope и Ruff трёх затронутых Python files — PASS.
  Старый full Ruff/CI boundary выше не изменился. Generic API и runtime skill
  просмотрены: API/ownership/protocol semantics от этой оптимизации не меняются.

Текущий runtime fingerprint (тот же алгоритм/57 files):
`a340e57458653efdfe526a82844baa0ca69cf88724f997fcb66f8034a0d87fe6`.
Текущий tests fingerprint (79 files):
`e91dd386bd89ea1b6b875e692a47870eae23066012e365d3d67f5e8fcabbbb92`.
Предыдущие 995 PASS/fingerprints выше относятся к checkpoint до этого исправления.

## Dracula window and terminal-reserved F10 — 2026-10-16

Позднее уточнение оператора заменяет прежний цветовой вариант и F10-view:
оформить именно окно передачи/confirmation в Dracula, F10 полностью убрать без
новой клавиши или Ctrl+T binding. Полноэкранный viewer имени и его paging удалены;
имя переносится/сокращается только визуально, полный basename сохранён в FT1
snapshot/log. Более ранние описания F10 выше — история предыдущего checkpoint.

Палитра сверена с [официальным Dracula palette](https://draculatheme.com/contribute).
В curses используются ближайшие ANSI-256 indices: foreground 255, background 236,
purple 141; выбранная кнопка — dark-on-purple с bold, заголовок bold.
На 8/16-color terminal используется white/black/magenta fallback. Выделенные
pairs 8–10 принадлежат только file window/confirmation; остальное TUI и palette
терминального эмулятора не меняются. F10 отсутствует в source bindings/help.

Validation:

* Targeted TUI/window/real curses PTY: 116 PASS. Проверены отдельные pairs,
  цвета body/frame/title/selection, default Да и F10 без изменения file/input.
* `python -m compileall -q src serialterminal.py usb_timing_logger.py tools scripts`
  и Ruff затронутых Python files — PASS. Новая API/ownership семантика не добавлена;
  AGENT_API.md и runtime skill просмотрены, остаются согласованы.
* Full pytest: **1004 PASS / 97.55 s**, без skips. Full CI boundary по прежним F401/TODO_051 сохранён.
* Luna017 plan/scenario обновлены под Dracula и отсутствие F10;
  `--check-plan` PASS, никаких hardware operations.

Текущий runtime fingerprint (57 files):
`85a6175240f0bb8067a8f07c67e4259a64be9a322e28e50a6c4bce4a005acbc4`.
Текущий tests fingerprint (79 files):
`570f78ed2e796f1181cfb3f8952c1b131d93957b9d627bb554479b6677c067b4`.
Алгоритм тот же; более ранние fingerprints/999 PASS относятся к предыдущему UI.

## Hardware task and result

Луне подготовлен [017_tui_file_transfer/SCENARIO.md](/home/dream/coding/luna_runs/017_tui_file_transfer/SCENARIO.md),
plan.json, AGENTS.md и run/analyze entrypoints в формате существующих 007–016.
`--check-plan` — PASS, 8 checks specified, hardware_started=false.
Readiness **SPECIFIED_NOT_IMPLEMENTED**: перед исполнением нужен PTY hardware
harness настоящего ST TUI + peer agent, --execute сейчас сохраняет preparation
BLOCKED без ST. Обычный JSONL file smoke не выдаётся за TUI validation.
Прежние suites и `_support` не менялись. Радио здесь не запускалось.

Implemented: YES. Software: 1009 PASS, compile PASS, changed-file Ruff PASS; full CI gate отдельно OPEN.
Status: IMPLEMENTED / hardware validation OPEN. Не CLOSED.

## Автозакрытие успешной передачи — 2026-10-16

По уточнению оператора `completed` автоматически закрывает progress window
и compact header для TX/RX. Это frontend transition, не новый FT1 outcome:
успех по-прежнему требует verified RESULT/durable publication. Failed/cancelled
остаются видны. F7 явно возвращает сохранённый completed; следующий sync не
закрывает его повторно. Новый active ROOT снова открывает окно.

Если успех пришёл при открытом confirmation, progress закрывается, но видимое
малое уведомление остаётся до Enter/Esc: старое подтверждение не попадёт в input
и не отменит следующий ROOT. Такой boundary покрыт software regression и
добавлен в Luna017 вместе с TX/RX autoclose и idle TUI BLE release subset.

Validation: **1009 PASS / 95.92 s**, без skips. Compileall src/entrypoints/tools/scripts
и Ruff изменённых autoclose source/test files — PASS. Это полный pytest, не full CI:
известные baseline F401 и общий CI parity gate TODO_051 остаются отдельно OPEN.
AGENT_API.md и runtime skill просмотрены: frontend-only autoclose не меняет
JSONL schema, ownership, transport или agent behavior, дополнительных API edits не нужно.

Runtime fingerprint (57 files, тот же path+NUL+bytes+NUL алгоритм):
`9dc2dd3a3069085e74fa90cad28eed8d9dfbd02dac998c7bed2dd3c2cc8af8a9`.
Tests fingerprint (79 files):
`3a98eb9e28e18dc25f4110690e3d222ba4b848705ef191c4fac06be714e85f30`.
Ни hardware acceptance, ни CLOSED здесь не заявлены.

## Подтверждённая отмена закрывает окно — 2026-10-16

Уточнение оператора: RX Esc → Да останавливало передачу, но оставляло progress
до второго Esc. Причина: принятый cancel не менял frontend visibility; cancelled
сохранялся на экране как любой другой terminal result.

После принятого manager.cancel адресный ROOT закрывает progress сразу для TX/RX.
Асинхронный RX worker продолжает settlement независимо; скрытие окна не снимает
ownership и не разрешает radio mutations раньше времени. После cancelled compact
header также скрыт. F7 явно возвращает сохранённый outcome без повторного скрытия.
Новый ROOT открывается нормально. Если cancel отклонён, окно остаётся; поздний
cleanup failure снова показывает ошибку. Cancelled без подтверждённого локального
запроса сохраняет прежнее видимое представление. Прежние описания «cancelled
остаётся виден» выше относятся к старому checkpoint и этому последнему случаю.

Validation:

- Новая регрессия сначала **4 FAIL** на старой реализации: TX/RX confirmation и
  асинхронные RX cancelled/failed. Затем выбранный TUI/window/PTY subset —
  **127 PASS / 1.87 s**.
- Настоящий curses/PTY теперь проверяет обе роли TX/RX: Esc → Да закрывает
  progress/header без второго Esc, F7 возвращает cancelled. Никаких устройств.
- Полный `pytest -q`: **1015 PASS / 99.14 s**, без skips.
- Compileall src/entrypoints/tools/scripts, changed-file Ruff и diff --check — PASS.
- AGENT_API.md и runtime skill явно просмотрены: cooperative cancel, ownership
  и JSONL API не менялись. Это frontend-only исправление.
- Luna017 plan/scenario обновлены, offline --check-plan PASS; аппаратный harness
  остаётся SPECIFIED_NOT_IMPLEMENTED, hardware validation OPEN.

Runtime fingerprint (57 files, прежний path+NUL+bytes+NUL алгоритм):
`9142e11cbd9550f2209601374146c57de5b0cba3533574dc75a9839a6bfa1496`.
Tests fingerprint (79 files):
`3c6d7810ce47f24fc577b0baac7e4a32d4f8c05cadce45fad56dd19231bdad33`.

Status: IMPLEMENTED / hardware validation OPEN; не CLOSED. Commit/push не выполнялись.

## Terminal status в чате и F7 только для active — 2026-10-16

Последнее уточнение оператора заменяет прежнее повторное открытие terminal
результата через F7. F7 toggles только active TX/RX; completed/failed/cancelled
не открывают старое окно. Terminal compact header также не остаётся сверху.
Success и подтверждённый local cancel закрывают progress как прежде; ошибка
может остаться видимой до Esc. Retained manager history не удаляется.

При terminal event ROOT сразу, независимо от окна/его закрытия/видимости,
появляется одна белая строка чата `[FT1] TX/RX «имя»: ...`: успешно, ошибка с
code/message либо прервано пользователем. Имена/reasons экранируют controls;
строка отделена от незавершённого входящего RX fragment. Цвет normal/white
сохраняется даже при ERROR/FAILED в имени/причине. Через write_output она
попадает в primary LOCAL log; никаких RF команд не создаётся.

Сообщение идёт из terminal event, не из redraw/display_snapshot transition:
промежуточный RESULT/progress не сообщает успех, service child не подменяет
ROOT. Для фильтра child используется public ROOT snapshot конкретного bound
manager/session. Повторный same-ID runtime attempt имеет собственный outcome.

Validation:

- Selected TUI/window/real curses PTY: **145 PASS / 2.14 s**. Настоящий curses
  проверяет TX/RX, три outcome, active/terminal F7 и атрибут белого chat status.
- Полный pytest финального snapshot: **1033 PASS / 98.38 s**, без skips.
  Предыдущие 1032 PASS относились к версии до RX-fragment boundary поправки.
- Changed-file Ruff, compileall src/entrypoints/tools/scripts и diff --check PASS.
- AGENT_API.md и runtime skill явно просмотрены; human LOCAL summary уточнён
  в API docs, JSONL schema/ownership/cooperative cancel не менялись.
  Dependency direction остаётся frontend → public FT1 manager/events.
- Luna017 plan/scenario обновлены: 10 checks specified, --check-plan PASS.
  Hardware harness по-прежнему не реализован; новый hardware PASS не заявляется.

Операторские logs `bad_logs/002/1-7` разобраны только Python streaming parser.
В этой сохранённой паре один ROOT `2.png`, 760052 original / 758496 wire bytes,
3342 DATA; TX/RX completed, RESULT OK, host local_replays=0. В sender log
22 ACK_SIZED_CRC + 22 отдельных REGs lines, 7 M1-RETRY/producer_busy; на peer
1 M1-RETRY/producer_busy. Новых ERROR classes, NUL, fatal/reboot в этой паре
не найдено. Это старое операторское evidence, не аппаратная проверка нового UI
и не доказательство причины CRC/радиоинтерференции. Исходные logs не менялись;
к нодам не обращались, текущему операторскому прогону не мешали.

Runtime fingerprint (57 files, прежний алгоритм):
`31ac53dc4f77fa18356e84112f4f032582307286a5da909788349b649757e3e1`.
Tests fingerprint (79 files):
`571d504b2e5224984dfacab1c69605e4f2dfd4f3825b4c893dfe6abb14e8a21c`.

Status: IMPLEMENTED / hardware validation OPEN. Не CLOSED. Commit/push не выполнялись.

## Локальный /clear, F9 help и видимый F4 — 2026-10-16

`/clear` + Enter в TUI вызывает тот же `_clear_output`, что F4: очищает output
и scrollback, возвращает FOLLOW, сохраняет logs и ROOT/session/manager/ownership.
Команда обрабатывается до controller classification/admission, поэтому доступна
при DATA, RX, repair, recovery, waiting_result и terminal settlement. На ноду
не отправляется, generic/chatter profiles не получают особого wire-command.
Точное `/clear` допускает окружающие пробелы; аргументы не входят в local alias.
Typed command потребляется и остаётся в history; F4 сохраняет текущий input draft.
F9 добавляет local TUI help с /clear/F4; прежний device help сохранён. Нижняя
строка начинается с F4 Clear в generic и file-capable режиме, видна на 80 columns.

Validation:

- До implementation новая regression active `/clear` — **1 FAIL**, воспроизведён
  отказ очистки из-за FT1 mutation gate.
- Selected TUI/window/real curses PTY — **165 PASS / 1.79 s**; дополнительный
  settling-ownership test включён в финальный полный набор. Реальный curses/PTY
  проверяет TX/RX, local /clear без TX/cancel, неизменность bytes primary log,
  отсутствие старого текста и видимость F4 Clear в нижней строке.
- Первый полный прогон: **1053 PASS / 1 FAIL / 108.32 s**. Сбой в существующем
  `test_observe_default_avoids_raw_event_payload_amplification`: ожидал 65 событий,
  получил 66. В сохранённом fake agent log — 65 RX плюс позднее TX settlement
  startup `/m1` (seq=70). TUI/clear в этом тесте не участвуют.
  Evidence: `/tmp/pytest-of-dream/pytest-33/test_observe_default_avoids_ra0/agent.log`.
- Отдельный повтор этого теста — **1 PASS / 0.34 s**. Повтор полного pytest на
  неизменном source/test snapshot — **1054 PASS / 98.08 s**, без skips.
  Agent implementation и этот test не изменялись/не ослаблялись.
- Changed-file Ruff, compileall src/entrypoints/tools/scripts и diff --check PASS.
- AGENT_API.md и runtime skill явно проверены: новый local TUI alias не является
  JSONL op и не меняет agent send_line semantics/ownership. ARCHITECTURE.md,
  README.md и FILE_TRANSFER.md согласованы с frontend-local dispatcher.
- Luna017 расширена: 11 checks specified, --check-plan PASS. Hardware validation
  остаётся OPEN; ноды/BlueZ не открывались и текущий операторский прогон не менялся.

Runtime fingerprint (57 files, прежний path+NUL+bytes+NUL алгоритм):
`bc177f6e758cc1a6ce8993bf2ed0550b88cc9504891ed5aa628cf6d29bc706cd`.
Tests fingerprint (79 files):
`7bc9c266be12a800981fb33549cbd87467b2c487e21f5981931b51100d22a954`.

Status: IMPLEMENTED / hardware validation OPEN. Не CLOSED. Commit/push не выполнялись.
