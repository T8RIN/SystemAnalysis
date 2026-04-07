:- encoding(utf8).

% ===================================================
% Проект на выбор (№3 из списка):
% Поиск нарушений по автомобилю
% ===================================================

% violation(Автомобиль, Тип_нарушения, Время).
violation('А123ВС116', speed_limit, 202604011030).
violation('А123ВС116', red_light, 202604031540).
violation('В456ОР116', wrong_parking, 202604021115).
violation('К777ХХ116', no_seatbelt, 202604041200).

% find_violations_by_car(Автомобиль, СписокНарушений)
% Возвращает список всех нарушений для выбранного авто.
find_violations_by_car(Car, Violations) :-
    findall(
        row(Car, Type, Time),
        violation(Car, Type, Time),
        Violations
    ).

% show_violations_by_car(Автомобиль)
% Печатает все нарушения по выбранному авто.
show_violations_by_car(Car) :-
    find_violations_by_car(Car, Violations),
    (   Violations = []
    ->  format('Для автомобиля ~w нарушений не найдено.~n', [Car])
    ;   (
            format('Нарушения для ~w:~n', [Car]),
            forall(
                member(row(_Car, Type, Time), Violations),
                format('- Тип: ~w, Время: ~w~n', [Type, Time])
            )
        )
    ).

% Примеры запросов:
% ?- find_violations_by_car('А123ВС116', L).
% ?- show_violations_by_car('А123ВС116').
% ?- show_violations_by_car('М001ТТ116').
