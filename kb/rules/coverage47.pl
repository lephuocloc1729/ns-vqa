/*  Phase 4.7 step 1b (owner, 2026-11-17: additive only): who a sign is addressed to.

    covers(?S, +Veh, -T): sign S's effect is addressed to vehicle Veh, by the vehicle checks
    of assess/6 only (vehicle, exception, plate). Time, day, scope and lane say when and where
    a sign applies, not to whom, so they are left out. T is true, false or unknown.
    The effect comes from the catalog row as for forbids/5: bans (art. 22, effective_prohibits/4
    with local plates), mandatory directions (art. 32, every vehicle) and maximum speeds (B.27).
*/

:- multifile leaf/1.
:- discontiguous leaf/1.
:- discontiguous covers/3.

covers(S, Veh, T) :-
    scene_sign(S, Code),
    effective_prohibits(S, Code, _, Specs),
    cite(r_prohibition),
    who_truth(S, Code, Specs, Veh, T).
covers(S, Veh, T) :-
    scene_sign(S, Code),
    direction_sign(Code),
    catalog_sign(Code, _, _, _),
    cite(r_mandatory_direction),
    who_truth(S, Code, [spec(vehicle, [])], Veh, T).
covers(S, Veh, T) :-
    scene_sign(S, Code),
    max_speed_for(Code, C),
    cite(r_max_speed),
    who_truth(S, Code, [spec(C, [])], Veh, T).

% Lane boards (P.127b / P.127c, B.27b / B.27c): the rows' vehicles ("any" = every vehicle).
covers(S, Veh, T) :-
    scene_sign(S, Code),
    lane_board(Code),
    lane_limit(S, _, Spec, _),
    cite(r_max_speed),
    lane_row_truth(Spec, Veh, T).

lane_row_truth(any, _, true).
lane_row_truth(Spec, Veh, T) :-
    Spec \== any,
    any_spec_match([Spec], Veh, T).

% A sign with no vehicle-specific effect is addressed to every road user ("người tham gia giao
% thông"): art. 27 (warnings), art. 31 (mandatory signs), art. 35 (guide signs).
covers(S, _Veh, true) :-
    scene_sign(S, Code),
    catalog_sign(Code, Cat, _, _),
    all_users_rule(Cat, Rule),
    \+ prohibits(Code, _, _),
    \+ direction_sign(Code),
    \+ max_speed_for(Code, _),
    cite(Rule).

all_users_rule(warning,     r_warning_all_users).
all_users_rule(mandatory,   r_mandatory_all_users).
all_users_rule(information, r_guide_all_users).

who_truth(S, Code, Specs, Veh, T) :-
    assess(S, Code, Specs, Veh, ctx(unknown, unknown, unknown),
           [vehicle-T1, exception-T2, plate-T3|_]),
    and3([T1, T2, T3], T).

%!  q_covers(+SignId:string, +Veh, -Out) is det.
%   Out = _{verdict: yes | no | unknown | none, reasons: [...]}: yes when some effect of the
%   sign is surely addressed to Veh, unknown when one may be, no when none is, none when the
%   sign has no effect covers/3 models. Every solution is returned with its proof.
q_covers(SS, Veh, _{verdict:V, reasons:Rs}) :-
    atom_string(S, SS),
    findall(R-T, ( prove(covers(S, Veh, T), P), proof_root(covers(S, Veh, T), P, D),
                   reason_dict(S, T, D, R) ), RTs),
    findall(R, member(R-_, RTs), Rs),
    findall(T, member(_-T, RTs), Ts),
    (   Ts == [] -> V = none
    ;   memberchk(true, Ts) -> V = yes
    ;   memberchk(unknown, Ts) -> V = unknown
    ;   V = no
    ).
