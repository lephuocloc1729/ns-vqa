/*  Loads the whole knowledge base. Python consults this file once per process.
    Facts from kb/sign_catalog.yaml are asserted afterwards by vqa.reasoning.engine.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

:- ensure_loaded(meta).
:- ensure_loaded(scene).
:- ensure_loaded(ontology).
:- ensure_loaded('rules/common').
:- ensure_loaded('rules/prohibitions').
:- ensure_loaded('rules/speed').
:- ensure_loaded('rules/mandatory').
:- ensure_loaded('rules/identity').
:- ensure_loaded('rules/zones').
:- ensure_loaded('rules/coverage47').
:- ensure_loaded('rules/general47').
:- ensure_loaded('rules/signals47').
:- ensure_loaded('rules/v13_47').
:- ensure_loaded(query).
