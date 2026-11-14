/*  Rule family: prohibitions (QCVN 41:2024 art. 22 + appendix B) and the
    mandatory-direction signs that imply prohibitions (art. 32 + D.1a).

    forbids(+Action, +Veh, +Ctx, -S, -T): sign S forbids Action for Veh in Ctx
    with truth T (true or unknown).

    clears(+Action, +Veh, +Ctx, -S, -Why): sign S restricts Action in general
    but does not forbid it here; Why names the check that failed. These are
    the proofs behind a "yes" answer.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% A prohibitory sign forbids an action for its vehicle classes, unless excepted,
% restricted by its plates, or out of force (time window, day parity, scope).
forbids(Action, Veh, Ctx, S, T) :-
    scene_sign(S, Code),
    prohibits(Code, Action, Specs),
    cite(r_prohibition),
    applies(S, Code, Specs, Veh, Ctx, T).

% A mandatory-direction sign (R.301 family) forbids the directions it does not list.
forbids(Action, Veh, Ctx, S, T) :-
    direction_action(Action),
    scene_sign(S, Code),
    direction_sign(Code),
    \+ only_direction(Code, Action),
    catalog_sign(Code, _, _, _),
    cite(r_mandatory_direction),
    applies(S, Code, [spec(vehicle, [])], Veh, Ctx, T).

% ---- why a sign that concerns the action does not forbid it

clears(Action, Veh, Ctx, S, Why) :-
    scene_sign(S, Code),
    prohibits(Code, Action, Specs),
    cite(r_prohibition),
    assess(S, Code, Specs, Veh, Ctx, Checks),
    first_false(Checks, Why).

clears(Action, Veh, Ctx, S, Why) :-
    direction_action(Action),
    scene_sign(S, Code),
    direction_sign(Code),
    catalog_sign(Code, _, _, _),
    cite(r_mandatory_direction),
    direction_check(Code, Action, T0),
    assess(S, Code, [spec(vehicle, [])], Veh, Ctx, Checks),
    first_false([direction-T0|Checks], Why).

%!  direction_check(+Code, +Action, -T) is det.  true = the sign forbids this direction.
direction_check(Code, Action, false) :-
    only_direction(Code, Action).
direction_check(Code, Action, true) :-
    \+ only_direction(Code, Action).

%!  unrelated_sign(+Action, -S) is nondet.
%   A prohibitory or mandatory sign that does not concern Action at all. Used to
%   explain a "yes" when no sign in the scene concerns the action.
unrelated_sign(Action, S) :-
    scene_sign(S, Code),
    catalog_sign(Code, Cat, _, _),
    restricting_category(Cat),
    \+ prohibits(Code, Action, _),
    \+ ( direction_sign(Code), direction_action(Action) ).

restricting_category(prohibitory).
restricting_category(mandatory).
