/*  Rule family: prohibitions (QCVN 41:2024 art. 22 + appendix B) and the
    mandatory-direction signs that imply prohibitions (art. 32 + D.1a).

    forbids(+Action, +Veh, +Ctx, -S, -T): sign S forbids Action for Veh in Ctx
    with truth T (true or unknown). No solution means no sign forbids it.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% A prohibitory sign forbids an action for a vehicle class, unless excepted,
% restricted by its plates, or out of force (time window, day parity, scope).
forbids(Action, Veh, Ctx, S, T) :-
    scene_sign(S, Code),
    prohibits(Code, Action, Spec),
    cite(r_prohibition),
    applies(S, Code, Spec, Veh, Ctx, T).

% A mandatory-direction sign (R.301 family) forbids the directions it does not list.
forbids(Action, Veh, Ctx, S, T) :-
    direction_action(Action),
    scene_sign(S, Code),
    direction_sign(Code),
    \+ only_direction(Code, Action),
    catalog_sign(Code, _, _, _),
    cite(r_mandatory_direction),
    applies(S, Code, spec(vehicle, []), Veh, Ctx, T).
