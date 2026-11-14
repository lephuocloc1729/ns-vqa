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
cmp_truth(_, X, _, unknown) :- X == unknown, !.
cmp_truth(_, _, Y, unknown) :- Y == unknown, !.
cmp_truth(Op, X, Y, T) :- ( cmp(Op, X, Y) -> T = true ; T = false ).

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
%!  sign_specs(+S, +Code, +Spec0, -Spec) is det.
%   Add the condition read from the sign's number (catalog value_cond/4) to Spec0.
%   A sign that should carry a number but has none gives an `unknown` condition.
sign_specs(S, Code, spec(C, Conds0), spec(C, Conds)) :- !,
    findall(c(A, Op, V), ( value_cond(Code, VC, A, Op),
                           subclass_of(C, VC),
                           ( sign_value(S, V) -> true ; V = unknown ) ), Extra),
    append(Conds0, Extra, Conds).
sign_specs(_, _, Spec, Spec).

% --------------------------------------------------------------------------
% Exceptions and vehicle plates
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

%!  not_excepted(+S, +Code, +Veh, -T) is semidet.  Fails when Veh is surely excepted.
not_excepted(S, Code, Veh, T) :-
    exception_truth(S, Code, Veh, E),
    not3(E, T),
    T \== false.

%!  plate_scope(+S, +Veh, -T) is semidet.  An S.505a plate limits the sign to its vehicles.
plate_scope(S, _, true) :-
    \+ plate_vehicle(S, _).
plate_scope(S, Veh, T) :-
    has_vehicle_plate(S),
    cite(r_vehicle_plate),
    vehicle_plate_specs(S, Specs),
    any_spec_match(Specs, Veh, T),
    T \== false.

leaf(has_vehicle_plate(_)).
has_vehicle_plate(S) :- plate_vehicle(S, _), !.

leaf(vehicle_plate_specs(_, _)).
vehicle_plate_specs(S, Specs) :- findall(Sp, plate_vehicle(S, Sp), Specs).

% --------------------------------------------------------------------------
% When is a sign in force (rule family: time-window plates)
% --------------------------------------------------------------------------

%!  in_force(+S, +Code, +Ctx, -T) is semidet.  Fails when the sign is surely not in force.
in_force(S, Code, Ctx, T) :-
    time_in_force(S, Ctx, T1),
    day_in_force(S, Code, Ctx, T2),
    scope_open(Code, T3),
    and3([T1, T2, T3], T),
    T \== false.

time_in_force(S, _, true) :-
    \+ plate_time(S, _, _).
time_in_force(S, ctx(M, _), T) :-
    has_time_plate(S),
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

day_in_force(S, Code, _, true) :-
    \+ sign_days(S, Code, _).
day_in_force(S, Code, ctx(_, D), T) :-
    sign_days(S, Code, P),
    day_truth(D, P, T).

sign_days(S, _, P)    :- plate_days(S, P).
sign_days(S, Code, P) :- \+ plate_days(S, _), catalog_days(Code, P).

leaf(day_truth(_, _, _)).
day_truth(D, _, unknown) :- D == unknown, !.
day_truth(D, even, T) :- ( D mod 2 =:= 0 -> T = true ; T = false ).
day_truth(D, odd, T)  :- ( D mod 2 =:= 1 -> T = true ; T = false ).

%!  scope_open(+Code, -T) is det.
%   A still image cannot show whether we are before or after an end-of-restriction
%   sign that is visible together with the restriction, so that case is unknown.
scope_open(Code, true) :-
    \+ ended_in_scene(Code, _).
scope_open(Code, unknown) :-
    ended_once(Code).

ended_in_scene(Code, E) :-
    scene_sign(E, EC),
    ends(EC, Code).

leaf(ended_once(_)).
ended_once(Code) :- ended_in_scene(Code, _), !.

% --------------------------------------------------------------------------
% Lanes
% --------------------------------------------------------------------------

leaf(lane_truth(_, _, _)).
%!  lane_truth(+AskedLane, +SignLane, -T) is det.  AskedLane may be unknown.
lane_truth(L, _, unknown) :- L == unknown, !.
lane_truth(L, L1, T) :- ( L =:= L1 -> T = true ; T = false ).

%!  lane_scope(+S, +Lane, -T) is semidet.  A sign over one lane (S.504) applies only there.
lane_scope(S, _, true) :-
    \+ sign_lane(S, _).
lane_scope(S, Lane, T) :-
    sign_lane(S, L),
    cite(r_lane_plate),
    lane_truth(Lane, L, T),
    T \== false.

% --------------------------------------------------------------------------
% Applicability of one sign to one vehicle in one context
% --------------------------------------------------------------------------

%!  applies(+S, +Code, +Spec, +Veh, +Ctx, -T) is semidet.
%   Fails when the sign surely does not apply; T is true or unknown otherwise.
applies(S, Code, Spec0, Veh, Ctx, T) :-
    sign_specs(S, Code, Spec0, Spec),
    spec_match(Spec, Veh, T1), T1 \== false,
    not_excepted(S, Code, Veh, T2),
    plate_scope(S, Veh, T3),
    in_force(S, Code, Ctx, T4),
    and3([T1, T2, T3, T4], T).
