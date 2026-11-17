/*  Rule family: speed limits, overall and by lane (QCVN 41:2024 B.27, B.27b,
    B.27c, D.6) and lanes reserved for vehicle classes (D.14, B.27c).

    speed_violation(+Veh, +Speed, +Lane, +Ctx, -S, -T): driving Veh at Speed
    km/h on Lane breaks sign S (T = true or unknown). Lane may be `unknown`.
    speed_clears(+Veh, +Speed, +Lane, +Ctx, -S, -Why): speed sign S is not broken.

    lane_block(+Veh, +Lane, +Ctx, -S, -T): sign S closes Lane to Veh.
    lane_clears(+Veh, +Lane, +Ctx, -S, -Why): lane sign S leaves Lane open to Veh.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% Maximum speed sign (P.127, P.127a), optionally limited to some lanes.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    max_speed_sign(Veh, Speed, Lane, Ctx, S, Checks),
    checks_truth(Checks, T),
    T \== false.

% Minimum speed sign (R.306).
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    min_speed_sign(Veh, Speed, Lane, Ctx, S, Checks),
    checks_truth(Checks, T),
    T \== false.

% Lane board (P.127b, P.127c): per-lane maximum, optionally per vehicle group.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_prohibition),
    lane_limit(S, L, Spec, Max),
    Speed > Max,
    lane_truth(Lane, L, T0), T0 \== false,
    applies(S, Code, [Spec], Veh, Ctx, T1),
    and3([T0, T1], T).

% Lane board: per-lane minimum.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_prohibition),
    lane_min(S, L, Spec, Min),
    Speed < Min,
    lane_truth(Lane, L, T0), T0 \== false,
    applies(S, Code, [Spec], Veh, Ctx, T1),
    and3([T0, T1], T).

% Default speeds by road type (kb/rules/zones.pl, Circular 38/2024, interpretations).
speed_violation(Veh, Speed, _Lane, Ctx, S, T) :-
    default_violation(Veh, Speed, Ctx, S, T).

% Lane is the lane in Ctx; assess/6 checks it against the lanes the sign covers.
max_speed_sign(Veh, Speed, _Lane, Ctx, S, [limit-T0|Checks]) :-
    scene_sign(S, Code),
    max_speed_for(Code, Class),
    cite(r_prohibition),
    cite(r_max_speed),
    catalog_sign(Code, _, _, _),
    limit_value(S, Max),
    cmp_truth(gt, Speed, Max, T0),
    assess(S, Code, [spec(Class, [])], Veh, Ctx, Checks).

min_speed_sign(Veh, Speed, _Lane, Ctx, S, [limit-T0|Checks]) :-
    scene_sign(S, Code),
    min_speed_for(Code, Class),
    cite(r_min_speed),
    catalog_sign(Code, _, _, _),
    limit_value(S, Min),
    cmp_truth(lt, Speed, Min, T0),
    assess(S, Code, [spec(Class, [])], Veh, Ctx, Checks).

% ---- the binding limit (rule family: speed limits, value query)

%!  limit_candidate(+Veh, +Ctx, +Kind, -S, -V, -T) is nondet.
%   Sign S sets a Kind (max | min) limit V for Veh in Ctx (T = true or unknown).
limit_candidate(Veh, Ctx, max, S, V, T) :-
    scene_sign(S, Code),
    max_speed_for(Code, Class),
    cite(r_prohibition),
    cite(r_max_speed),
    catalog_sign(Code, _, _, _),
    sign_value(S, V),
    applies(S, Code, [spec(Class, [])], Veh, Ctx, T).
limit_candidate(Veh, Ctx, min, S, V, T) :-
    scene_sign(S, Code),
    min_speed_for(Code, Class),
    cite(r_min_speed),
    catalog_sign(Code, _, _, _),
    sign_value(S, V),
    applies(S, Code, [spec(Class, [])], Veh, Ctx, T).
limit_candidate(Veh, Ctx, Kind, S, V, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_prohibition),
    board_limit(Kind, S, L, Spec, V),
    Ctx = ctx(_, _, Lane),
    lane_truth(Lane, L, T0), T0 \== false,
    applies(S, Code, [Spec], Veh, Ctx, T1),
    and3([T0, T1], T).

limit_candidate(Veh, Ctx, Kind, S, V, T) :-
    default_limit_value(Veh, Ctx, Kind, S, V, T).

board_limit(max, S, L, Spec, V) :- lane_limit(S, L, Spec, V).
board_limit(min, S, L, Spec, V) :- lane_min(S, L, Spec, V).

leaf(limit_value(_, _)).
%!  limit_value(+S, -V) is det.  The number on the sign, or unknown if it was not read.
limit_value(S, V) :- ( sign_value(S, V0) -> V = V0 ; V = unknown ).

% ---- why a speed sign is not broken

speed_clears(Veh, Speed, Lane, Ctx, S, Why) :-
    max_speed_sign(Veh, Speed, Lane, Ctx, S, Checks),
    first_false(Checks, Why).
speed_clears(Veh, Speed, Lane, Ctx, S, Why) :-
    min_speed_sign(Veh, Speed, Lane, Ctx, S, Checks),
    first_false(Checks, Why).
speed_clears(Veh, Speed, _Lane, Ctx, S, Why) :-
    default_clears(Veh, Speed, Ctx, S, Why).
speed_clears(Veh, Speed, Lane, Ctx, S, within_limit) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_prohibition),
    \+ speed_violation(Veh, Speed, Lane, Ctx, S, _).

% ---- lanes open only to some vehicles (P.127c board, R.412 family)

lane_block(Veh, Lane, Ctx, S, T) :-
    lane_sign_checks(Veh, Lane, Ctx, S, Checks),
    checks_truth(Checks, T),
    T \== false.

lane_clears(_Veh, Lane, _Ctx, S, lane_not_covered) :-
    scene_sign(S, Code),
    lane_restricting(Code),
    catalog_sign(Code, _, _, _),
    \+ lane_has_specs(S, Lane).
lane_clears(Veh, Lane, Ctx, S, Why) :-
    lane_sign_checks(Veh, Lane, Ctx, S, Checks),
    first_false(Checks, Why).

lane_sign_checks(Veh, Lane, Ctx, S, [lane_closed-T0, exception-T1, time-T2, day-T3]) :-
    scene_sign(S, Code),
    lane_restricting(Code),
    catalog_sign(Code, _, _, _),
    lane_has_specs(S, Lane),
    lane_specs(S, Lane, Specs),
    vehicle_basis(Veh),
    any_spec_match(Specs, Veh, M),
    not3(M, T0),
    exception_check(S, Code, Veh, T1),
    time_check(S, Ctx, T2),
    day_check(S, Code, Ctx, T3).

% P.127c boards cite their own article (B.27c, via catalog_sign); R.412 signs cite D.14.
lane_restricting(Code) :- lane_board(Code).
lane_restricting(Code) :- lane_reserved_sign(Code), cite(r_lane_reserved).

leaf(lane_reserved_sign(_)).
lane_reserved_sign(Code) :- lane_reserved(Code, _), !.

leaf(lane_has_specs(_, _)).
lane_has_specs(S, Lane) :- lane_vehicle(S, Lane, _), !.

leaf(lane_specs(_, _, _)).
lane_specs(S, Lane, Specs) :- findall(Sp, lane_vehicle(S, Lane, Sp), Specs).
