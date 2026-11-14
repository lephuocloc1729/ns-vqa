/*  Domain ontology (DESIGN.md layer 2).

    Vehicle classes follow Law 36/2024/QH15 art. 34 and the class wording in
    the QCVN 41:2024 sign articles. Must stay in sync with
    vqa.schemas.VehicleClass.
*/

% is_a(Sub, Super)
is_a(motor_vehicle,   vehicle).
is_a(rudimentary,     vehicle).
is_a(special_machine, vehicle).

is_a(car,             motor_vehicle).
is_a(motorbike,       motor_vehicle).
is_a(motor_tricycle,  motor_vehicle).   % xe lam, xích lô máy

is_a(passenger_car,   car).
is_a(taxi,            passenger_car).
is_a(bus,             car).
is_a(city_bus,        bus).             % xe buýt (R.412a: "kể cả ô tô buýt")
is_a(coach,           bus).             % xe khách that is not a xe buýt (P.107a bans it)
is_a(truck,           car).

is_a(motorcycle,      motorbike).       % xe mô tô hai bánh
is_a(moped,           motorbike).       % xe gắn máy
is_a(sidecar,         motorbike).       % xe máy 3 bánh có thùng

is_a(tractor,         special_machine). % Law 36 art. 34(3)(c)

is_a(bicycle,         rudimentary).
is_a(cargo_bicycle,   rudimentary).
is_a(cyclo,           rudimentary).
is_a(hand_cart,       rudimentary).
is_a(animal_cart,     rudimentary).

% pedestrian is a road user but not a vehicle: P.101 does not ban pedestrians (B.1 c).
road_user(pedestrian).
road_user(C) :- subclass_of(C, vehicle).

%!  subclass_of(?Sub, ?Super) is nondet.  Reflexive, transitive closure of is_a/2.
subclass_of(C, C).
subclass_of(C, S) :- is_a(C, M), subclass_of(M, S).

strict_subclass_of(C, S) :- subclass_of(C, S), C \== S.

% Directions covered by the mandatory-direction signs (R.301 family).
direction_action(go_straight).
direction_action(turn_left).
direction_action(turn_right).

action(enter). action(go_straight). action(turn_left). action(turn_right).
action(u_turn). action(overtake). action(stop). action(park). action(honk).
