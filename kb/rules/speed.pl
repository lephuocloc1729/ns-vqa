/*  Rule family: speed limits, overall and by lane (QCVN 41:2024 B.27, B.27b,
    B.27c, D.6) and lanes reserved for vehicle classes (D.14, B.27c).

    speed_violation(+Veh, +Speed, +Lane, +Ctx, -S, -T): driving Veh at Speed
    km/h on Lane breaks sign S (T = true or unknown). Lane may be `unknown`.

    lane_block(+Veh, +Lane, +Ctx, -S, -T): sign S closes Lane to Veh.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% Maximum speed sign (P.127, P.127a), optionally limited to one lane by S.504.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    max_speed_for(Code, Class),
    cite(r_max_speed),
    catalog_sign(Code, _, _, _),
    limit_value(S, Max),
    cmp_truth(gt, Speed, Max, T0), T0 \== false,
    lane_scope(S, Lane, T1),
    applies(S, Code, spec(Class, []), Veh, Ctx, T2),
    and3([T0, T1, T2], T).

% Minimum speed sign (R.306).
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    min_speed_for(Code, Class),
    cite(r_min_speed),
    limit_value(S, Min),
    cmp_truth(lt, Speed, Min, T0), T0 \== false,
    lane_scope(S, Lane, T1),
    applies(S, Code, spec(Class, []), Veh, Ctx, T2),
    and3([T0, T1, T2], T).

% Lane board (P.127b, P.127c): per-lane maximum, optionally per vehicle group.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    lane_limit(S, L, Spec, Max),
    Speed > Max,
    lane_truth(Lane, L, T0), T0 \== false,
    applies(S, Code, Spec, Veh, Ctx, T1),
    and3([T0, T1], T).

% Lane board: per-lane minimum.
speed_violation(Veh, Speed, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    catalog_sign(Code, _, _, _),
    lane_min(S, L, Spec, Min),
    Speed < Min,
    lane_truth(Lane, L, T0), T0 \== false,
    applies(S, Code, Spec, Veh, Ctx, T1),
    and3([T0, T1], T).

leaf(limit_value(_, _)).
%!  limit_value(+S, -V) is det.  The number on the sign, or unknown if it was not read.
limit_value(S, V) :- ( sign_value(S, V0) -> V = V0 ; V = unknown ).

% A lane listed on a P.127c board or under an R.412 sign is open only to the
% vehicles named for it.
lane_block(Veh, Lane, Ctx, S, T) :-
    scene_sign(S, Code),
    lane_restricting(Code),
    catalog_sign(Code, _, _, _),
    lane_has_specs(S, Lane),
    cite(r_lane_reserved),
    lane_specs(S, Lane, Specs),
    any_spec_match(Specs, Veh, M),
    not3(M, T0), T0 \== false,
    not_excepted(S, Code, Veh, T1),
    in_force(S, Code, Ctx, T2),
    and3([T0, T1, T2], T).

lane_restricting(Code) :- lane_board(Code).
lane_restricting(Code) :- lane_reserved_sign(Code).

leaf(lane_reserved_sign(_)).
lane_reserved_sign(Code) :- lane_reserved(Code, _), !.

leaf(lane_has_specs(_, _)).
lane_has_specs(S, Lane) :- lane_vehicle(S, Lane, _), !.

leaf(lane_specs(_, _, _)).
lane_specs(S, Lane, Specs) :- findall(Sp, lane_vehicle(S, Lane, Sp), Specs).
