/*  vqa.reasoning.facts reads the plate text into plate_except_day(S, Kind),
    Kind in mon..sun or holiday; the engine asserts the asked date as query_day_kind(Kind)
    (its weekday, plus holiday or maybe_holiday). The plate is S.H,6-like (F.17), so it cites
    r_exception_plate. Which dates are public holidays is a calendar fact computed in Python
    (vqa.reasoning.engine._day_kinds: the fixed solar holidays; Tết and Hùng Kings' day are lunar,
    so January to April dates are maybe_holiday), not a traffic rule; flagged for the owner.

    Without an asked date the plate is not applied (status quo before this fix; a question with
    a time but no date keeps its answer).
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

%!  except_day_check(+S, -T) is det.  true = the asked day is not excepted by S's plates.
except_day_check(S, true) :-
    \+ plate_except_day(S, _).
except_day_check(S, T) :-
    has_except_day(S),
    cite(r_exception_plate),
    excepted_today(S, E),
    not3(E, T).

leaf(has_except_day(_)).
has_except_day(S) :- plate_except_day(S, _), !.

%!  excepted_today(+S, -T) is det.  T = true when the asked day is one the plate excepts.
leaf(excepted_today(_, _)).
excepted_today(_, false) :- \+ query_day_kind(_), !.
excepted_today(S, true) :- plate_except_day(S, K), query_day_kind(K), !.
excepted_today(S, unknown) :- plate_except_day(S, holiday), query_day_kind(maybe_holiday), !.
excepted_today(_, false).

% ---- reserved lanes: "xe buýt" on a bus-and-coach lane (owner, 2026-11-20; parser v18 lane_reserved_is)
% R.412a (QCVN 41:2024/BGTVT, D.14) reserves the lane for coaches "kể cả ô tô buýt": every kind of
% bus is meant alike, so a question that names one kind (city_bus, coach) asks about the lane's own
% class. Only for reserved-lane signs whose class is listed here; a lane for all cars (R.412f) stays
% not reserved for passenger cars, as trucks may use it too.
lane_reserved_group(bus).

%!  q_lane_reserved_group(+Lane, +Class, -Groups) is det.
%   The listed reserved-lane classes Class belongs to on Lane: their kinds count as one vehicle there.
q_lane_reserved_group(Lane, Class, Groups) :-
    findall(G, ( lane_vehicle(S, Lane, spec(G, _)), scene_sign(S, Code), lane_reserved_sign(Code),
                 lane_reserved_group(G), subclass_of(Class, G) ), Gs),
    sort(Gs, Groups).
