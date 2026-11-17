/*  Fact predicates: the sign catalog (asserted once from kb/sign_catalog.yaml by
    vqa.kb.Catalog.facts) and the current scene (asserted per query by
    vqa.reasoning.facts.scene_facts). All are dynamic so Python can load them.
*/

% ---- catalog facts (one set per process)
:- dynamic catalog_sign/4,       % catalog_sign(Code, Category, LawId, ArticleId)
           prohibits/3,          % prohibits(Code, Action, [spec(Class, Conds), ...])
           catalog_except/2,     % catalog_except(Code, Class)
           no_priority_exempt/1, % no_priority_exempt(Code)
           value_cond/4,         % value_cond(Code, Class, Attr, Op)
           catalog_days/2,       % catalog_days(Code, even|odd)
           max_speed_for/2,      % max_speed_for(Code, Class)
           min_speed_for/2,      % min_speed_for(Code, Class)
           lane_board/1,         % lane_board(Code)
           lane_reserved/2,      % lane_reserved(Code, Class)
           direction_sign/1,     % direction_sign(Code)
           only_direction/2,     % only_direction(Code, Action)
           ends/2,               % ends(EndCode, EndedCode)
           standard_placement/2, % standard_placement(Code, before_intersection|after_intersection)
           placement_effect/4,   % placement_effect(Code, Placement, Directions, Scope)
           class_interpretation/3, % class_interpretation(Class, LawId, ArticleId)
           attr_interpretation/1,  % attr_interpretation(Rule), e.g. load_implies_gross
           catalog_key/2,        % catalog_key(Code, Key)
           catalog_tag/2,        % catalog_tag(Code, Tag)
           zone_sign/3,          % zone_sign(Code, expressway|residential, start|end)   phase 4.5 F4
           conduct/2,            % conduct(Code, What)       F5, used by stage B's conduct intent
           permits_here/2,       % permits_here(Code, Action) F6 (I.409 u_turn, I.408 park)
           pass_side/2,          % pass_side(Code, as_shown)  F3b (R.302)
           yield_from/2,         % yield_from(Code, left)     F3c (R.303)
           informational/1.      % informational(Code)        F7 (orders nothing)

% ---- scene facts (replaced for every query)
:- dynamic sign/3,               % sign(S, Code, Confidence)
           sign_value/2,         % sign_value(S, Number)
           sign_lane/3,          % sign_lane(S, Lane, plate|position)  S.504 plate or position.lane
           sign_placement/2,     % sign_placement(S, before_intersection|after_intersection)
           plate_time/3,         % plate_time(S, FromMin, ToMin)   S.508, minutes after midnight
           plate_days/2,         % plate_days(S, even|odd)     S.508
           plate_vehicle/2,      % plate_vehicle(S, Spec)      S.505a
           plate_except/2,       % plate_except(S, Spec)       S.H,6
           local_plate/2,        % local_plate(S, Text)      non-standard plate (not in QCVN 41)
           local_vehicle/2,      % local_vehicle(S, Spec)    replaces the sign's own vehicles
           local_action/2,       % local_action(S, Action)   replaces the sign's own actions
           group/2,              % group(S, G)               condition groups (Sign.rules)
           group_vehicle/3,      % group_vehicle(S, G, Spec)
           group_time/4,         % group_time(S, G, FromMin, ToMin)
           group_days/3,         % group_days(S, G, even|odd)
           lane_limit/4,         % lane_limit(S, Lane, Spec|any, MaxKmh)
           lane_min/4,           % lane_min(S, Lane, Spec|any, MinKmh)
           lane_vehicle/3,       % lane_vehicle(S, Lane, Spec)  lane open only to these
           scene_vehicle/5,      % scene_vehicle(V, Class, Lane|unknown, Action, Speed|unknown)
           selected/1,           % selected(S): restrict reasoning to these signs
           selection_active/0,
           road_divided/1,       % road_divided(true|false): the scene's road has a divider (phase 4.5)
           unread_sign/1.        % unread_sign(S): a sign that couldn't be read (not a warning triangle)

scene_fact(sign/3).        scene_fact(sign_value/2).   scene_fact(sign_lane/3).
scene_fact(sign_placement/2).
scene_fact(plate_time/3).  scene_fact(plate_days/2).   scene_fact(plate_vehicle/2).
scene_fact(plate_except/2). scene_fact(lane_limit/4).  scene_fact(lane_min/4).
scene_fact(lane_vehicle/3). scene_fact(scene_vehicle/5).
scene_fact(group/2).       scene_fact(group_vehicle/3). scene_fact(group_time/4).
scene_fact(group_days/3).
scene_fact(local_plate/2). scene_fact(local_vehicle/2). scene_fact(local_action/2).
scene_fact(selected/1).    scene_fact(selection_active/0).
scene_fact(road_divided/1). scene_fact(unread_sign/1).

catalog_fact(catalog_sign/4). catalog_fact(prohibits/3). catalog_fact(catalog_except/2).
catalog_fact(no_priority_exempt/1). catalog_fact(value_cond/4). catalog_fact(catalog_days/2).
catalog_fact(max_speed_for/2). catalog_fact(min_speed_for/2). catalog_fact(lane_board/1).
catalog_fact(lane_reserved/2). catalog_fact(direction_sign/1). catalog_fact(only_direction/2).
catalog_fact(ends/2). catalog_fact(standard_placement/2). catalog_fact(placement_effect/4).
catalog_fact(class_interpretation/3). catalog_fact(attr_interpretation/1). catalog_fact(catalog_key/2). catalog_fact(catalog_tag/2).
catalog_fact(zone_sign/3). catalog_fact(conduct/2). catalog_fact(permits_here/2).
catalog_fact(pass_side/2). catalog_fact(yield_from/2). catalog_fact(informational/1).

clear_scene :-
    forall(scene_fact(N/A), (functor(H, N, A), retractall(H))).

clear_catalog :-
    forall(catalog_fact(N/A), (functor(H, N, A), retractall(H))).

%!  add_facts(+Text:string) is det.  Assert a Prolog list of facts written by Python.
add_facts(Text) :-
    term_string(Facts, Text),
    must_be(list, Facts),
    forall(member(F, Facts), assertz(F)).

% ---- for the meta-interpreter
fact_pred(G) :-
    functor(G, N, A),
    (   scene_fact(N/A) ; catalog_fact(N/A) ; ontology_fact(N/A) ), !.

ontology_fact(is_a/2).

%!  fact_source(+Fact, -Source) is det.  Catalog facts cite the sign's article.
fact_source(class_interpretation(_, L, A), src(L, A)) :- !.
fact_source(G, src(L, A)) :-
    functor(G, N, Ar), catalog_fact(N/Ar),
    arg(1, G, Code), atom(Code),
    catalog_sign(Code, _, L, A), !.
fact_source(G, scene) :-
    functor(G, N, A), scene_fact(N/A), !.
fact_source(_, none).

%!  scene_sign(?S, ?Code) is nondet.  Signs in the scene, honouring a selection.
scene_sign(S, Code) :-
    sign(S, Code, _),
    (   selection_active
    ->  selected(S)
    ;   true
    ).
