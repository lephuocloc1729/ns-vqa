/*  Rule family: mandatory directions by placement (QCVN 41:2024 art. 32 + D.1a).

    D.1a says what each R.301 sign allows, and where, depending on whether it
    stands before or after the intersection (catalog placement_effect/4):
      intersection_behind      placed before: applies at the intersection behind the sign
      intersection_ahead       placed after: applies at the intersection in front of the sign
      until_next_intersection  R.301a placed after: from the sign to the next intersection

    required(+Action, +Veh, +Placement, +Ctx, -S, -T): sign S makes Action the only
    allowed direction (T true or unknown). Placement is the one asked about, or
    `unknown`: then the sign's placement in the scene, else its standard placement.
    requirement_clears(+Action, +Veh, +Placement, +Ctx, -S, -Why): S does not require it.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

required(Action, Veh, P0, Ctx, S, T) :-
    requirement(Action, Veh, P0, Ctx, S, Checks),
    checks_truth(Checks, T),
    T \== false.

requirement_clears(Action, Veh, P0, Ctx, S, Why) :-
    requirement(Action, Veh, P0, Ctx, S, Checks),
    first_false(Checks, Why).

requirement(Action, Veh, P0, Ctx, S, [required-T0|Checks]) :-
    scene_sign(S, Code),
    direction_sign(Code),
    catalog_sign(Code, _, _, _),
    cite(r_mandatory_direction),
    placement_for(S, Code, P0, P),
    requirement_truth(Code, P, Action, T0),
    assess(S, Code, [spec(vehicle, [])], Veh, Ctx, Checks).

%!  placement_for(+S, +Code, +Asked, -P) is det.  Asked, else scene, else standard, else unknown.
placement_for(S, Code, P0, P) :-
    (   P0 \== unknown -> P = P0
    ;   sign_placement(S, P1) -> P = P1
    ;   standard_placement(Code, P2) -> P = P2
    ;   P = unknown
    ).

leaf(requirement_truth(_, _, _, _)).
%!  requirement_truth(+Code, +Placement, +Action, -T) is det.
%   true when Action is the only direction the sign allows at that placement.
%   With an unknown placement, every placement D.1a describes is tried; if they
%   disagree the answer is unknown. A placement D.1a does not describe is unknown.
requirement_truth(Code, P, Action, T) :-
    (   P == unknown
    ->  findall(Px, placement_effect(Code, Px, _, _), Ps)
    ;   Ps = [P]
    ),
    findall(Ti, ( member(Px, Ps),
                  (   placement_effect(Code, Px, Dirs, _)
                  ->  ( Dirs == [Action] -> Ti = true ; Ti = false )
                  ;   Ti = unknown ) ), Ts),
    (   Ts == [] -> T = unknown
    ;   sort(Ts, [T]) -> true
    ;   T = unknown
    ).

%!  requirement_detail(+S, +Placement, -Dict) is det.  What the sign allows, and where.
requirement_detail(S, P0, _{sign_id:SS, placement:PS, standard:StS, directions:DsS, scope:ScS}) :-
    scene_sign(S, Code),
    atom_string(S, SS),
    placement_for(S, Code, P0, P),
    atom_string(P, PS),
    ( standard_placement(Code, St) -> atom_string(St, StS) ; StS = "either" ),
    (   placement_effect(Code, P, Dirs, Scope)
    ->  maplist([D, X]>>atom_string(D, X), Dirs, DsS), atom_string(Scope, ScS)
    ;   DsS = [], ScS = "not_described"
    ).
