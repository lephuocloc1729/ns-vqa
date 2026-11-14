/*  Shared pieces for all rule families: three-valued truth, vehicle matching,
    exceptions, plates, and when a sign is in force.

    Truth values are true, false and unknown. Unknown facts (missing time of
    day, missing vehicle weight, ...) are kept open: they make a conclusion
    unknown, never false (DESIGN.md, "Symbolic scene graph").

    Vehicles are veh(Class, Attrs) with Attrs a list of a(Attr, Value); an
    attribute that is not listed is unknown. Contexts are ctx(Minute, Day):
    minute of the day and day of the month, either may be `unknown`.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% --------------------------------------------------------------------------
% Rule sources (law_id + article_id, same format as the dataset's relevant_articles)
% --------------------------------------------------------------------------

rule_source(r_prohibition,         'QCVN 41:2024/BGTVT', '22').
rule_source(r_mandatory_direction, 'QCVN 41:2024/BGTVT', '32').
rule_source(r_time_plate,          'QCVN 41:2024/BGTVT', 'F.10').
rule_source(r_vehicle_plate,       'QCVN 41:2024/BGTVT', 'F.5').
rule_source(r_exception_plate,     'QCVN 41:2024/BGTVT', 'F.17').
rule_source(r_lane_plate,          'QCVN 41:2024/BGTVT', 'F.4').
rule_source(r_max_speed,           'QCVN 41:2024/BGTVT', 'B.27').
rule_source(r_min_speed,           'QCVN 41:2024/BGTVT', 'D.6').
rule_source(r_lane_reserved,       'QCVN 41:2024/BGTVT', 'D.14').
rule_source(r_aux_plate,           'QCVN 41:2024/BGTVT', '41').

% --------------------------------------------------------------------------
% Three-valued logic (leaves: evaluated directly, shown as one proof node)
% --------------------------------------------------------------------------

leaf(and3(_, _)).
and3(Ts, false)   :- memberchk(false, Ts), !.
and3(Ts, unknown) :- memberchk(unknown, Ts), !.
and3(_, true).

leaf(or3(_, _)).
or3(Ts, true)    :- memberchk(true, Ts), !.
or3(Ts, unknown) :- memberchk(unknown, Ts), !.
or3(_, false).

leaf(not3(_, _)).
not3(true, false).
not3(false, true).
not3(unknown, unknown).

leaf(cmp_truth(_, _, _, _)).
%!  cmp_truth(+Op, +X, +Y, -T) is det.  `unknown` operands give unknown.
%   X may be an interval iv(Lo, LoIn, Hi, HiIn) (only bounds known): true when every
%   value in it satisfies the comparison, false when none does, unknown otherwise.
cmp_truth(_, X, _, unknown) :- X == unknown, !.
cmp_truth(_, _, Y, unknown) :- Y == unknown, !.
cmp_truth(Op, iv(Lo, LI, Hi, HI), Y, T) :- !,
    (   iv_all(Op, Lo, LI, Hi, HI, Y) -> T = true
    ;   iv_none(Op, Lo, LI, Hi, HI, Y) -> T = false
    ;   T = unknown
    ).
cmp_truth(Op, X, Y, T) :- ( cmp(Op, X, Y) -> T = true ; T = false ).

% every value v in the interval has v Op Y
iv_all(gt, Lo, LI, _, _, Y) :- ( Lo > Y ; Lo =:= Y, LI == false ).
iv_all(ge, Lo, _, _, _, Y)  :- Lo >= Y.
iv_all(lt, _, _, Hi, HI, Y) :- ( Hi < Y ; Hi =:= Y, HI == false ).
iv_all(le, _, _, Hi, _, Y)  :- Hi =< Y.
% no value v in the interval has v Op Y
iv_none(gt, _, _, Hi, _, Y)  :- Hi =< Y.
iv_none(ge, _, _, Hi, HI, Y) :- ( Hi < Y ; Hi =:= Y, HI == false ).
iv_none(lt, Lo, _, _, _, Y)  :- Lo >= Y.
iv_none(le, Lo, LI, _, _, Y) :- ( Lo > Y ; Lo =:= Y, LI == false ).

cmp(gt, X, Y) :- X > Y.
cmp(ge, X, Y) :- X >= Y.
cmp(lt, X, Y) :- X < Y.
cmp(le, X, Y) :- X =< Y.

% --------------------------------------------------------------------------
% Vehicle specs
% --------------------------------------------------------------------------

veh_attr(veh(_, Attrs), A, V) :- memberchk(a(A, V), Attrs), !.
veh_attr(_, _, unknown).

leaf(class_truth(_, _, _)).
%!  class_truth(+SpecClass, +VehClass, -T) is det.
%   true if the vehicle is of the class, unknown if the vehicle class is broader
%   (e.g. asking about "ô tô" against a truck ban), false otherwise.
class_truth(C, VC, true)    :- subclass_of(VC, C), !.
class_truth(C, VC, unknown) :- strict_subclass_of(C, VC), !.
class_truth(_, _, false).

leaf(spec_match(_, _, _)).
%!  spec_match(+Spec, +Veh, -T) is det.  Spec = spec(Class, Conds) | any.
spec_match(any, _, true) :- !.
spec_match(spec(C, Conds), Veh, T) :-
    Veh = veh(VC, _),
    class_truth(C, VC, T0),
    (   T0 == false
    ->  T = false
    ;   findall(Tc, ( member(c(A, Op, V), Conds),
                      veh_attr(Veh, A, X),
                      cmp_truth(Op, X, V, Tc) ), Tcs),
        and3([T0|Tcs], T)
    ).

leaf(any_spec_match(_, _, _)).
any_spec_match(Specs, Veh, T) :-
    findall(Ti, (member(Sp, Specs), spec_match(Sp, Veh, Ti)), Ts),
    or3(Ts, T).

leaf(sign_specs(_, _, _, _)).
%!  sign_specs(+S, +Code, +Specs0, -Specs) is det.
%   Add the condition read from the sign's number (catalog value_cond/4) to each spec.
%   A sign that should carry a number but has none gives an `unknown` condition.
sign_specs(S, Code, Specs0, Specs) :-
    maplist(sign_spec(S, Code), Specs0, Specs).

sign_spec(S, Code, spec(C, Conds0), spec(C, Conds)) :- !,
    findall(c(A, Op, V), ( value_cond(Code, VC, A, Op),
                           subclass_of(C, VC),
                           ( sign_value(S, V) -> true ; V = unknown ) ), Extra),
    append(Conds0, Extra, Conds).
sign_spec(_, _, Spec, Spec).

% --------------------------------------------------------------------------
% Checks. Each returns a truth value instead of failing, so the same checks
% explain both why a sign applies (forbids) and why it does not (clears).
% A check is "true" when it lets the sign apply.
% --------------------------------------------------------------------------

leaf(exception_truth(_, _, _, _)).
%!  exception_truth(+S, +Code, +Veh, -T) is det.  Is Veh excepted from sign S?
exception_truth(_, Code, Veh, true) :-
    veh_attr(Veh, priority, true),
    \+ no_priority_exempt(Code), !.
exception_truth(S, Code, Veh, T) :-
    Veh = veh(VC, _),
    findall(Ti, ( catalog_except(Code, EC), class_truth(EC, VC, Ti) ), T1),
    findall(Ti, ( plate_except(S, Sp), spec_match(Sp, Veh, Ti) ), T2),
    append(T1, T2, Ts),
    or3(Ts, T).

%!  exception_check(+S, +Code, +Veh, -T) is det.  true = Veh is not excepted.
exception_check(S, Code, Veh, T) :-
    (   has_except_plate(S)
    ->  cite(r_aux_plate), cite(r_exception_plate)
    ;   true
    ),
    exception_truth(S, Code, Veh, E),
    not3(E, T).

leaf(has_except_plate(_)).
has_except_plate(S) :- plate_except(S, _), !.

%!  plate_check(+S, +Veh, -T) is det.  An S.505a plate limits the sign to its vehicles.
plate_check(S, _, true) :-
    \+ plate_vehicle(S, _).
plate_check(S, Veh, T) :-
    has_vehicle_plate(S),
    cite(r_aux_plate),
    cite(r_vehicle_plate),
    vehicle_plate_specs(S, Specs),
    any_spec_match(Specs, Veh, T).

leaf(has_vehicle_plate(_)).
has_vehicle_plate(S) :- plate_vehicle(S, _), !.

leaf(vehicle_plate_specs(_, _)).
vehicle_plate_specs(S, Specs) :- findall(Sp, plate_vehicle(S, Sp), Specs).

% ---- rule family: time-window plates (S.508, F.10)

%!  time_check(+S, +Ctx, -T) is det.  true = inside a time window (or no time plate).
time_check(S, _, true) :-
    \+ plate_time(S, _, _).
time_check(S, ctx(M, _), T) :-
    has_time_plate(S),
    cite(r_aux_plate),
    cite(r_time_plate),
    window_truth(S, M, T).

leaf(has_time_plate(_)).
has_time_plate(S) :- plate_time(S, _, _), !.

leaf(window_truth(_, _, _)).
%!  window_truth(+S, +Minute, -T) is det.  Minute inside any of the sign's windows?
%   Windows include both ends ("6h-22h" covers 22:00) and may run past midnight.
window_truth(_, M, unknown) :- M == unknown, !.
window_truth(S, M, T) :-
    (   plate_time(S, F, To), in_window(M, F, To)
    ->  T = true
    ;   T = false
    ).

in_window(M, F, T) :- F =< T, M >= F, M =< T.
in_window(M, F, T) :- F > T, ( M >= F ; M =< T ).

%!  day_check(+S, +Code, +Ctx, -T) is det.  true = right day parity (or none required).
day_check(S, Code, _, true) :-
    \+ sign_days(S, Code, _).
day_check(S, Code, ctx(_, D), T) :-
    has_day_plate(S),
    cite(r_aux_plate),
    cite(r_time_plate),
    sign_days(S, Code, P),
    day_truth(D, P, T).
day_check(S, Code, ctx(_, D), T) :-
    \+ plate_days(S, _),
    catalog_days(Code, P),
    day_truth(D, P, T).

leaf(has_day_plate(_)).
has_day_plate(S) :- plate_days(S, _), !.

sign_days(S, _, P)    :- plate_days(S, P).
sign_days(S, Code, P) :- \+ plate_days(S, _), catalog_days(Code, P).

leaf(day_truth(_, _, _)).
day_truth(D, _, unknown) :- D == unknown, !.
day_truth(D, even, T) :- ( D mod 2 =:= 0 -> T = true ; T = false ).
day_truth(D, odd, T)  :- ( D mod 2 =:= 1 -> T = true ; T = false ).

%!  scope_check(+Code, -T) is det.
%   A still image cannot show whether we are before or after an end-of-restriction
%   sign that is visible together with the restriction, so that case is unknown.
scope_check(Code, true) :-
    \+ ended_in_scene(Code, _).
scope_check(Code, unknown) :-
    ended_once(Code).

ended_in_scene(Code, E) :-
    scene_sign(E, EC),
    ends(EC, Code).

leaf(ended_once(_)).
ended_once(Code) :- ended_in_scene(Code, _), !.

% ---- lanes

leaf(lane_truth(_, _, _)).
%!  lane_truth(+AskedLane, +SignLane, -T) is det.  AskedLane may be unknown.
lane_truth(L, _, unknown) :- L == unknown, !.
lane_truth(L, L1, T) :- ( L =:= L1 -> T = true ; T = false ).

%!  lane_check(+S, +Lane, -T) is det.
%   A sign over some lanes (S.504 plate, or mounted over them) applies only there.
lane_check(S, _, true) :-
    \+ sign_lane(S, _, _).
lane_check(S, Lane, T) :-
    has_sign_lane(S),
    (   has_lane_plate(S)
    ->  cite(r_aux_plate), cite(r_lane_plate)
    ;   true
    ),
    sign_lanes_truth(S, Lane, T).

leaf(has_sign_lane(_)).
has_sign_lane(S) :- sign_lane(S, _, _), !.

leaf(has_lane_plate(_)).
has_lane_plate(S) :- sign_lane(S, _, plate), !.

leaf(sign_lanes_truth(_, _, _)).
sign_lanes_truth(S, Lane, T) :-
    findall(Ti, ( sign_lane(S, L, _), lane_truth(Lane, L, Ti) ), Ts),
    or3(Ts, T).

% --------------------------------------------------------------------------
% Applicability of one sign to one vehicle in one context
% --------------------------------------------------------------------------

%!  assess(+S, +Code, +Specs, +Veh, +Ctx, -Checks) is det.
%   Checks = [vehicle-T, exception-T, plate-T, time-T, day-T, scope-T].
assess(S, Code, Specs0, Veh, Ctx,
       [vehicle-T1, exception-T2, plate-T3, time-T4, day-T5, scope-T6]) :-
    sign_specs(S, Code, Specs0, Specs),
    vehicle_basis(Veh),
    any_spec_match(Specs, Veh, T1),
    exception_check(S, Code, Veh, T2),
    conditions_check(S, Code, Veh, Ctx, T3, T4, T5),
    scope_check(Code, T6).

%!  conditions_check(+S, +Code, +Veh, +Ctx, -Tvehicle, -Ttime, -Tday) is det.
%   Plates, or the sign's condition groups when it has them.
conditions_check(S, Code, Veh, Ctx, Tv, Tt, Td) :-
    \+ group(S, _),
    plate_check(S, Veh, Tv),
    time_check(S, Ctx, Tt),
    day_check(S, Code, Ctx, Td).
conditions_check(S, Code, Veh, Ctx, Tv, Tt, Td) :-
    has_groups(S),
    cite(r_aux_plate),
    (   has_group_vehicles(S) -> cite(r_vehicle_plate) ; true ),
    (   has_group_times(S) -> cite(r_time_plate) ; true ),
    groups_truth(S, Code, Veh, Ctx, Tv, Tt, Td).

leaf(has_groups(_)).
has_groups(S) :- group(S, _), !.
leaf(has_group_vehicles(_)).
has_group_vehicles(S) :- group_vehicle(S, _, _), !.
leaf(has_group_times(_)).
has_group_times(S) :- group_time(S, _, _, _), !.

leaf(groups_truth(_, _, _, _, _, _, _)).
%!  groups_truth(+S, +Code, +Veh, +Ctx, -Tv, -Tt, -Td) is det.
%   The sign applies when some group matches both vehicle and time (and day).
%   Tv: some group's vehicles match; Tt: some group matches vehicle and time;
%   Td: some group matches vehicle, time and day. Td is the exact answer.
groups_truth(S, Code, Veh, ctx(M, D), Tv, Tt, Td) :-
    findall(V-T-Dy, ( group(S, G),
                      group_vehicle_truth(S, G, Veh, V),
                      group_time_truth(S, G, M, T),
                      group_day_truth(S, G, Code, D, Dy) ), Rows),
    findall(V, member(V-_-_, Rows), Vs), or3(Vs, Tv),
    findall(X, ( member(V-T-_, Rows), and3([V, T], X) ), Ts), or3(Ts, Tt),
    findall(X, ( member(V-T-Dy, Rows), and3([V, T, Dy], X) ), Ds), or3(Ds, Td).

group_vehicle_truth(S, G, Veh, T) :-
    findall(Sp, group_vehicle(S, G, Sp), Specs),
    ( Specs == [] -> T = true ; any_spec_match(Specs, Veh, T) ).

group_time_truth(S, G, M, T) :-
    (   \+ group_time(S, G, _, _) -> T = true
    ;   M == unknown -> T = unknown
    ;   group_time(S, G, F, To), in_window(M, F, To) -> T = true
    ;   T = false
    ).

group_day_truth(S, G, Code, D, T) :-
    (   group_days(S, G, P) -> true
    ;   catalog_days(Code, P) -> true
    ;   P = none
    ),
    ( P == none -> T = true ; day_truth(D, P, T) ).

%!  applies(+S, +Code, +Specs, +Veh, +Ctx, -T) is semidet.
%   Fails when the sign surely does not apply; T is true or unknown otherwise.
applies(S, Code, Specs, Veh, Ctx, T) :-
    assess(S, Code, Specs, Veh, Ctx, Checks),
    checks_truth(Checks, T),
    T \== false.

%!  vehicle_basis(+Veh) is det.
%   A vehicle class that is our interpretation of the law (class_interpretation/3)
%   is shown in the proof with its source, so the reading is visible and cited.
vehicle_basis(veh(C, _)) :-
    (   interpreted_class(C)
    ->  class_interpretation(C, _, _)
    ;   true
    ).

leaf(interpreted_class(_)).
interpreted_class(C) :- class_interpretation(C, _, _), !.

leaf(checks_truth(_, _)).
checks_truth(Checks, T) :-
    findall(Ti, member(_-Ti, Checks), Ts),
    and3(Ts, T).

leaf(first_false(_, _)).
%!  first_false(+Checks, -Why) is semidet.  Why the sign does not apply.
first_false(Checks, Why) :-
    member(Name-false, Checks), !,
    why_name(Name, Why).

why_name(vehicle,     vehicle_not_covered).
why_name(exception,   excepted).
why_name(plate,       plate_vehicle_not_covered).
why_name(time,        outside_time_window).
why_name(day,         wrong_day).
why_name(limit,       within_limit).
why_name(lane,        lane_not_covered).
why_name(lane_closed, vehicle_allowed_on_lane).
why_name(direction,   direction_allowed).
why_name(required,    not_the_only_direction).
