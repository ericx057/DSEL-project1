# OpenCAD UMMDB Multihop Retrieval QA Questions

- Repository: `https://github.com/nathan-sharp/OpenCAD.git`
- Commit: `89ebcba48ebb2f162b66702fc4797c9843ec5f64`
- Draft version: `0.1`
- Question sets: `5`
- Total questions: `250`

## Set 1 (seed 104729)

S01-Q001. For instance `inst_bracket_01`, connect the assembly source URI to the referenced artifact and report `uct[2].type`.
S01-Q002. In `examples/bracket_stress_result.ocr`, field `Von_Mises_Stress` points to which bufferView index, name, component type, and buffer URI?
S01-Q003. Cross-check the policy docs: which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?
S01-Q004. Use the example and schema together: `examples/bracket_stress_test.ocs` has what `header.generator` value, and under what schema title?
S01-Q005. In `examples/bracket_stress_test.ocs`, what value is stored at `results.status`, and what is the schema title for `.ocs`?
S01-Q006. For `.oce` data in `examples/wiring_demo.oce`, report `nets[1].nodes[1]` and the governing schema title.
S01-Q007. When validating `examples/bracket_stress_result.ocr`, what does `bufferViews[1].name` contain and what schema title should be used?
S01-Q008. When validating `examples/assembly_demo.oca`, what does `instances[0].transform[2]` contain and what schema title should be used?
S01-Q009. Use the OCR metadata and OCS setup: what simulation file produced the result, and what is load `load_force_01`?
S01-Q010. Cross-check `.ocp` between README and schema: what is the format name and the schema title?
S01-Q011. Use the OCR metadata and OCS setup: what simulation file produced the result, and what is load `load_gravity`?
S01-Q012. In `examples/bracket_stress_result.ocr`, what value is stored at `bufferViews[0].name`, and what is the schema title for `.ocr`?
S01-Q013. In `examples/assembly_demo.oca`, what value is stored at `instances[0].source_uri`, and what is the schema title for `.oca`?
S01-Q014. Using both cited governance/licensing artifacts, who is the current maintainer, and which governance section points readers to the maintainer list?
S01-Q015. Check `examples/wiring_demo.oce` against its schema: what is `components[0].part_number`, and which schema title applies?
S01-Q016. What is `header.generator` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S01-Q017. From the OCS target to the OCA metadata, give the source URI and assembly name.
S01-Q018. From `examples/assembly_demo.oca`, use `inst_sensor_01` to find its source URI, then give `components[1].footprint` from that source.
S01-Q019. Pair the sample value and schema: for `examples/bracket_demo.ocp`, give `uct[1].op_id` plus the schema title.
S01-Q020. From `examples/assembly_demo.oca`, use `inst_bracket_01` to find its source URI, then give `uct[1].params.sketch_ref` from that source.
S01-Q021. For the OpenCAD example `examples/wiring_demo.oce`, identify `nets[0].nodes[2]` and the matching schema title.
S01-Q022. What is `mesh.elements` in `examples/bracket_stress_result.ocr`, and what OpenCAD schema title covers that file extension?
S01-Q023. For production validation of `.ocr` artifacts, identify the schema path and the version string checked against headers.
S01-Q024. Using `examples/assembly_demo.oca` and its referenced source, what does instance `inst_sensor_01` point to and what is `nets[1].nodes[0]` there?
S01-Q025. For `.ocp` data in `examples/bracket_demo.ocp`, report `uct[1].type` and the governing schema title.
S01-Q026. For a multihop review of `inst_sensor_01`, what source URI is declared and what `components[2].part_number` value does the target expose?
S01-Q027. What is `instances[1].transform[5]` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S01-Q028. Using both cited governance/licensing artifacts, which license applies to `specification/` files, and which contribution rule repeats that license for specification changes?
S01-Q029. When the validator checks `.ocr`, which schema file is selected and what header version should pass?
S01-Q030. Which fields does `collect_relative_references` inspect, and which example result file uses one of those fields to point to a simulation?
S01-Q031. What file does `inst_bracket_01` in `examples/assembly_demo.oca` reference, and what value does that file give for `uct[1].params.distance`?
S01-Q032. Use the example and schema together: `examples/bracket_stress_result.ocr` has what `bufferViews[1].type` value, and under what schema title?
S01-Q033. For a production review of `.ocr`, what README description pairs with the schema title?
S01-Q034. For a production review of `.ocp`, what README description pairs with the schema title?
S01-Q035. Which OCIS domain does `.oce` represent in README, and what is the corresponding JSON Schema title?
S01-Q036. For the OpenCAD example `examples/bracket_demo.ocp`, identify `uct[0].type` and the matching schema title.
S01-Q037. Use the example and schema together: `examples/bracket_stress_test.ocs` has what `setup.boundary_conditions[0].target_entity` value, and under what schema title?
S01-Q038. Use the example and schema together: `examples/bracket_demo.ocp` has what `metadata.material` value, and under what schema title?
S01-Q039. For `.ocs` data in `examples/bracket_stress_test.ocs`, report `setup.loads[1].id` and the governing schema title.
S01-Q040. Check `examples/assembly_demo.oca` against its schema: what is `instances[0].transform[2]`, and which schema title applies?
S01-Q041. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `instances[1].id` plus the schema title.
S01-Q042. For `.ocs` examples, which schema path does the validator map to, and what repository VERSION must the example header match?
S01-Q043. Resolve this across repository policy files: what release criteria mention validation and self-consistency, and which README section describes repository validation checks?
S01-Q044. For extension `.ocr`, report the README description and the schema title that should validate files of that type.
S01-Q045. What is `bufferViews[0].byteOffset` in `examples/bracket_stress_result.ocr`, and what OpenCAD schema title covers that file extension?
S01-Q046. When validating `examples/bracket_stress_result.ocr`, what does `bufferViews[2].byteLength` contain and what schema title should be used?
S01-Q047. Pair the sample value and schema: for `examples/bracket_stress_result.ocr`, give `bufferViews[2].buffer` plus the schema title.
S01-Q048. Check `examples/bracket_demo.ocp` against its schema: what is `header.generator`, and which schema title applies?
S01-Q049. For a multihop review of `inst_bracket_01`, what source URI is declared and what `uct[1].type` value does the target expose?
S01-Q050. For a multihop review of `inst_bracket_01`, what source URI is declared and what `uct[2].op_id` value does the target expose?

## Set 2 (seed 104759)

S02-Q001. When validating `examples/bracket_stress_result.ocr`, what does `bufferViews[0].byteLength` contain and what schema title should be used?
S02-Q002. For a multihop review of `inst_sensor_01`, what source URI is declared and what `nets[0].nodes[0]` value does the target expose?
S02-Q003. Check `examples/assembly_demo.oca` against its schema: what is `constraints[1].target_a`, and which schema title applies?
S02-Q004. Check `examples/assembly_demo.oca` against its schema: what is `instances[0].transform[13]`, and which schema title applies?
S02-Q005. Use the example and schema together: `examples/assembly_demo.oca` has what `constraints[1].target_b` value, and under what schema title?
S02-Q006. Cross-check the policy docs: what release criteria mention validation and self-consistency, and which README section describes repository validation checks?
S02-Q007. In `examples/bracket_demo.ocp`, what value is stored at `uct[2].op_id`, and what is the schema title for `.ocp`?
S02-Q008. For `.oca` data in `examples/assembly_demo.oca`, report `instances[0].transform[10]` and the governing schema title.
S02-Q009. For the OpenCAD example `examples/bracket_demo.ocp`, identify `uct[2].op_id` and the matching schema title.
S02-Q010. Resolve this across repository policy files: which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?
S02-Q011. For the OpenCAD example `examples/wiring_demo.oce`, identify `nets[1].name` and the matching schema title.
S02-Q012. For `.ocs`, what domain name does the README assign, and what schema title governs that extension?
S02-Q013. For `.ocp` data in `examples/bracket_demo.ocp`, report `uct[1].op_id` and the governing schema title.
S02-Q014. Using `scripts/validate_repo.py` and VERSION, what schema validates `.oce` files and what version string is enforced?
S02-Q015. What does README call `.ocs`, and what is the title field in its schema?
S02-Q016. For `.ocp`, what domain name does the README assign, and what schema title governs that extension?
S02-Q017. For the OpenCAD example `examples/bracket_stress_result.ocr`, identify `bufferViews[0].name` and the matching schema title.
S02-Q018. Pair the sample value and schema: for `examples/bracket_stress_test.ocs`, give `setup.loads[0].target_entity` plus the schema title.
S02-Q019. For result `examples/bracket_stress_result.ocr`, trace `metadata.source_sim` and report the type and target entity for `load_gravity`.
S02-Q020. Use the example and schema together: `examples/wiring_demo.oce` has what `nets[1].nodes[0]` value, and under what schema title?
S02-Q021. Use the example and schema together: `examples/bracket_stress_test.ocs` has what `setup.loads[1].vector[1]` value, and under what schema title?
S02-Q022. For `.oca` data in `examples/assembly_demo.oca`, report `instances[0].transform[3]` and the governing schema title.
S02-Q023. When validating `examples/assembly_demo.oca`, what does `instances[0].transform[8]` contain and what schema title should be used?
S02-Q024. Cross-reference the validation script and VERSION: what schema path and expected version apply to `.ocp`?
S02-Q025. Trace `Von_Mises_Stress` from `fields.data` to `bufferViews` and `buffers` in `examples/bracket_stress_result.ocr`. What values are connected?
S02-Q026. In OpenCAD, what is the README-listed name for `.oca`, and which schema title backs it?
S02-Q027. Cross-check the policy docs: who is the current maintainer, and which governance section points readers to the maintainer list?
S02-Q028. From `examples/assembly_demo.oca`, use `inst_bracket_01` to find its source URI, then give `uct[1].params.direction[1]` from that source.
S02-Q029. Follow assembly instance `inst_bracket_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `uct[0].op_id` value is in the referenced file?
S02-Q030. From `examples/assembly_demo.oca`, use `inst_bracket_01` to find its source URI, then give `uct[2].op_id` from that source.
S02-Q031. Connect the result file to the simulation setup: give `source_sim`, `load_gravity` type, and its target entity.
S02-Q032. For `.ocr` data in `examples/bracket_stress_result.ocr`, report `buffers[0].uri` and the governing schema title.
S02-Q033. For the OpenCAD example `examples/assembly_demo.oca`, identify `instances[1].transform[5]` and the matching schema title.
S02-Q034. Resolve `inst_sensor_01` in the assembly and then read `nets[1].nodes[0]` from the referenced OpenCAD example.
S02-Q035. Check `examples/assembly_demo.oca` against its schema: what is `instances[0].transform[5]`, and which schema title applies?
S02-Q036. Using `examples/assembly_demo.oca` and its referenced source, what does instance `inst_sensor_01` point to and what is `metadata.board_name` there?
S02-Q037. For `.oca` examples, which schema path does the validator map to, and what repository VERSION must the example header match?
S02-Q038. Resolve `inst_bracket_01` in the assembly and then read `uct[1].params.direction[0]` from the referenced OpenCAD example.
S02-Q039. Check `examples/bracket_demo.ocp` against its schema: what is `uct[1].type`, and which schema title applies?
S02-Q040. For `.oca`, what domain name does the README assign, and what schema title governs that extension?
S02-Q041. For a production standards review, which license applies to `specification/` files, and which contribution rule repeats that license for specification changes?
S02-Q042. For the OpenCAD example `examples/wiring_demo.oce`, identify `nets[1].nodes[1]` and the matching schema title.
S02-Q043. In `examples/bracket_demo.ocp`, what value is stored at `uct[1].op_id`, and what is the schema title for `.ocp`?
S02-Q044. For `.ocp` data in `examples/bracket_demo.ocp`, report `uct[0].params.primitives[0].center[0]` and the governing schema title.
S02-Q045. What file does `inst_sensor_01` in `examples/assembly_demo.oca` reference, and what value does that file give for `metadata.board_name`?
S02-Q046. What three validation concerns does README list, and which script implements schema and cross-file reference checks?
S02-Q047. For `examples/bracket_stress_test.ocs`, which assembly file is targeted and what does that assembly call itself?
S02-Q048. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `instances[0].transform[7]` plus the schema title.
S02-Q049. In `examples/assembly_demo.oca`, what value is stored at `instances[0].transform[13]`, and what is the schema title for `.oca`?
S02-Q050. When validating `examples/wiring_demo.oce`, what does `nets[2].nodes[1]` contain and what schema title should be used?

## Set 3 (seed 104761)

S03-Q001. In `examples/bracket_stress_result.ocr`, what value is stored at `metadata.source_sim`, and what is the schema title for `.ocr`?
S03-Q002. For `.ocr`, what domain name does the README assign, and what schema title governs that extension?
S03-Q003. Connect `examples/bracket_stress_test.ocs` to its target artifact: what source URI is used, and what is the assembly name?
S03-Q004. Resolve `inst_bracket_01` in the assembly and then read `metadata.name` from the referenced OpenCAD example.
S03-Q005. From `examples/bracket_stress_result.ocr` back to its source simulation, what source_sim is recorded and what type is load `load_gravity`?
S03-Q006. Cross-check the policy docs: which governance rule requires an RFC issue for semantic or schema changes, and which contributing section gives examples of schema changes?
S03-Q007. Resolve `inst_bracket_01` in the assembly and then read `metadata.material` from the referenced OpenCAD example.
S03-Q008. Which OCIS domain does `.ocp` represent in README, and what is the corresponding JSON Schema title?
S03-Q009. which license applies to `specification/` files, and which contribution rule repeats that license for specification changes?
S03-Q010. What is `instances[0].transform[2]` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S03-Q011. For the OpenCAD example `examples/bracket_stress_result.ocr`, identify `bufferViews[1].name` and the matching schema title.
S03-Q012. For the OpenCAD example `examples/bracket_demo.ocp`, identify `uct[1].params.direction[1]` and the matching schema title.
S03-Q013. What is `components[1].ref_des` in `examples/wiring_demo.oce`, and what OpenCAD schema title covers that file extension?
S03-Q014. What does README call `.ocr`, and what is the title field in its schema?
S03-Q015. When validating `examples/bracket_stress_test.ocs`, what does `setup.boundary_conditions[0].target_entity` contain and what schema title should be used?
S03-Q016. What file does `inst_bracket_01` in `examples/assembly_demo.oca` reference, and what value does that file give for `uct[2].params.edges[0]`?
S03-Q017. What is `nets[2].name` in `examples/wiring_demo.oce`, and what OpenCAD schema title covers that file extension?
S03-Q018. For a multihop review of `inst_bracket_01`, what source URI is declared and what `uct[0].params.primitives[0].height` value does the target expose?
S03-Q019. Cross-check the policy docs: which license applies to `specification/` files, and which contribution rule repeats that license for specification changes?
S03-Q020. For extension `.ocp`, report the README description and the schema title that should validate files of that type.
S03-Q021. Follow assembly instance `inst_sensor_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `components[0].ref_des` value is in the referenced file?
S03-Q022. Follow assembly instance `inst_bracket_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `uct[2].params.radius` value is in the referenced file?
S03-Q023. Pair the sample value and schema: for `examples/bracket_stress_result.ocr`, give `header.version` plus the schema title.
S03-Q024. Cross-reference the validation script and VERSION: what schema path and expected version apply to `.ocr`?
S03-Q025. When validating `examples/wiring_demo.oce`, what does `nets[2].name` contain and what schema title should be used?
S03-Q026. Use the example and schema together: `examples/bracket_demo.ocp` has what `metadata.name` value, and under what schema title?
S03-Q027. Pair the sample value and schema: for `examples/bracket_stress_test.ocs`, give `setup.boundary_conditions[0].id` plus the schema title.
S03-Q028. For `.ocr` data in `examples/bracket_stress_result.ocr`, report `mesh.elements` and the governing schema title.
S03-Q029. What is `instances[0].transform[4]` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S03-Q030. Which simulation does `examples/bracket_stress_result.ocr` cite, and what load type is declared for `load_force_01` in that simulation?
S03-Q031. For a production standards review, which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?
S03-Q032. For the OpenCAD example `examples/assembly_demo.oca`, identify `instances[1].transform[8]` and the matching schema title.
S03-Q033. For `.ocs` data in `examples/bracket_stress_test.ocs`, report `setup.loads[0].vector[1]` and the governing schema title.
S03-Q034. What dependency installation command is documented before validation, and where does CI install the same requirements?
S03-Q035. For instance `inst_bracket_01`, connect the assembly source URI to the referenced artifact and report `uct[2].op_id`.
S03-Q036. For the OpenCAD example `examples/wiring_demo.oce`, identify `nets[2].nodes[0]` and the matching schema title.
S03-Q037. Check `examples/wiring_demo.oce` against its schema: what is `nets[2].nodes[1]`, and which schema title applies?
S03-Q038. Use the example and schema together: `examples/assembly_demo.oca` has what `instances[1].transform[4]` value, and under what schema title?
S03-Q039. In `examples/bracket_stress_test.ocs`, what value is stored at `setup.loads[0].type`, and what is the schema title for `.ocs`?
S03-Q040. For `.oce` examples, which schema path does the validator map to, and what repository VERSION must the example header match?
S03-Q041. For `.oce` data in `examples/wiring_demo.oce`, report `components[1].footprint` and the governing schema title.
S03-Q042. In OpenCAD, what is the README-listed name for `.ocs`, and which schema title backs it?
S03-Q043. Which OCR bufferView and raw buffer does `Von_Mises_Stress` use, including component type?
S03-Q044. In `examples/bracket_stress_test.ocs`, what value is stored at `setup.loads[0].id`, and what is the schema title for `.ocs`?
S03-Q045. In `examples/wiring_demo.oce`, what value is stored at `nets[0].nodes[2]`, and what is the schema title for `.oce`?
S03-Q046. For `.ocr` examples, which schema path does the validator map to, and what repository VERSION must the example header match?
S03-Q047. Using `examples/assembly_demo.oca` and its referenced source, what does instance `inst_bracket_01` point to and what is `uct[0].params.plane` there?
S03-Q048. Pair the sample value and schema: for `examples/bracket_stress_test.ocs`, give `metadata.name` plus the schema title.
S03-Q049. When validating `examples/assembly_demo.oca`, what does `instances[1].transform[4]` contain and what schema title should be used?
S03-Q050. Use the example and schema together: `examples/wiring_demo.oce` has what `components[2].part_number` value, and under what schema title?

## Set 4 (seed 104773)

S04-Q001. Use the OCR field and bufferView records: for `Von_Mises_Stress`, what data index, view name, component type, and buffer URI are used?
S04-Q002. When validating `.oce` content, what README domain name and schema title must be connected?
S04-Q003. Follow assembly instance `inst_sensor_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `nets[0].name` value is in the referenced file?
S04-Q004. Check `examples/assembly_demo.oca` against its schema: what is `instances[1].transform[2]`, and which schema title applies?
S04-Q005. Resolve `inst_sensor_01` in the assembly and then read `components[0].ref_des` from the referenced OpenCAD example.
S04-Q006. Follow assembly instance `inst_bracket_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `uct[2].params.edges[0]` value is in the referenced file?
S04-Q007. Check `examples/assembly_demo.oca` against its schema: what is `instances[0].transform[0]`, and which schema title applies?
S04-Q008. When the validator checks `.ocp`, which schema file is selected and what header version should pass?
S04-Q009. Check `examples/bracket_demo.ocp` against its schema: what is `metadata.material`, and which schema title applies?
S04-Q010. Check `examples/bracket_demo.ocp` against its schema: what is `uct[1].params.direction[1]`, and which schema title applies?
S04-Q011. For a multihop review of `inst_bracket_01`, what source URI is declared and what `uct[0].params.primitives[0].center[0]` value does the target expose?
S04-Q012. What is `metadata.name` in `examples/bracket_stress_test.ocs`, and what OpenCAD schema title covers that file extension?
S04-Q013. For `.oca` data in `examples/assembly_demo.oca`, report `metadata.assembly_name` and the governing schema title.
S04-Q014. For `.ocr` data in `examples/bracket_stress_result.ocr`, report `bufferViews[1].name` and the governing schema title.
S04-Q015. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `instances[0].transform[8]` plus the schema title.
S04-Q016. When validating `examples/bracket_stress_result.ocr`, what does `mesh.nodes` contain and what schema title should be used?
S04-Q017. Cross-check `.ocs` between README and schema: what is the format name and the schema title?
S04-Q018. When the validator checks `.oca`, which schema file is selected and what header version should pass?
S04-Q019. Which validation command is documented for contributors, and which GitHub workflow step runs the same repository validation script?
S04-Q020. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `instances[0].transform[11]` plus the schema title.
S04-Q021. When validating `examples/assembly_demo.oca`, what does `instances[1].transform[14]` contain and what schema title should be used?
S04-Q022. For `.ocr` data in `examples/bracket_stress_result.ocr`, report `bufferViews[2].byteLength` and the governing schema title.
S04-Q023. Use the example and schema together: `examples/bracket_demo.ocp` has what `uct[2].params.radius` value, and under what schema title?
S04-Q024. Using both cited governance/licensing artifacts, what release criteria mention validation and self-consistency, and which README section describes repository validation checks?
S04-Q025. Using `examples/assembly_demo.oca` and its referenced source, what does instance `inst_sensor_01` point to and what is `nets[2].nodes[1]` there?
S04-Q026. what release criteria mention validation and self-consistency, and which README section describes repository validation checks?
S04-Q027. In `examples/bracket_demo.ocp`, what value is stored at `uct[0].op_id`, and what is the schema title for `.ocp`?
S04-Q028. For a multihop review of `inst_sensor_01`, what source URI is declared and what `nets[1].name` value does the target expose?
S04-Q029. Follow assembly instance `inst_sensor_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `nets[0].nodes[3]` value is in the referenced file?
S04-Q030. In `examples/bracket_stress_result.ocr`, what value is stored at `mesh.elements`, and what is the schema title for `.ocr`?
S04-Q031. Use the example and schema together: `examples/bracket_stress_result.ocr` has what `header.generator` value, and under what schema title?
S04-Q032. What is `instances[0].id` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S04-Q033. For `.ocs` data in `examples/bracket_stress_test.ocs`, report `target.source_uri` and the governing schema title.
S04-Q034. What is `mesh.nodes` in `examples/bracket_stress_result.ocr`, and what OpenCAD schema title covers that file extension?
S04-Q035. Which OCIS domain does `.ocr` represent in README, and what is the corresponding JSON Schema title?
S04-Q036. In `examples/bracket_stress_result.ocr`, what value is stored at `fields[0].step`, and what is the schema title for `.ocr`?
S04-Q037. Trace `inst_bracket_01` across the assembly reference. Which source file is used, and what is the referenced file's `uct[1].params.direction[0]`?
S04-Q038. Map `.oce` from README to schemas: what name and title should a reviewer cite?
S04-Q039. For a production standards review, which governance rule requires an RFC issue for semantic or schema changes, and which contributing section gives examples of schema changes?
S04-Q040. Trace the simulation target from `examples/bracket_stress_test.ocs` to its assembly. What target URI is declared, and what assembly name is found?
S04-Q041. which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?
S04-Q042. When validating `examples/assembly_demo.oca`, what does `header.version` contain and what schema title should be used?
S04-Q043. Using the architecture table and schema file, identify the README name for `.ocp` and the schema title.
S04-Q044. Connect the result file to the simulation setup: give `source_sim`, `load_force_01` type, and its target entity.
S04-Q045. Use the example and schema together: `examples/bracket_stress_result.ocr` has what `mesh.element_type` value, and under what schema title?
S04-Q046. Check `examples/wiring_demo.oce` against its schema: what is `components[1].part_number`, and which schema title applies?
S04-Q047. For result `examples/bracket_stress_result.ocr`, trace `metadata.source_sim` and report the type and target entity for `load_force_01`.
S04-Q048. Check `examples/bracket_stress_result.ocr` against its schema: what is `bufferViews[2].name`, and which schema title applies?
S04-Q049. Using `scripts/validate_repo.py` and VERSION, what schema validates `.ocs` files and what version string is enforced?
S04-Q050. For `.ocp` data in `examples/bracket_demo.ocp`, report `uct[2].params.edges[0]` and the governing schema title.

## Set 5 (seed 104779)

S05-Q001. From `examples/bracket_stress_result.ocr` back to its source simulation, what source_sim is recorded and what type is load `load_force_01`?
S05-Q002. For `.oca` data in `examples/assembly_demo.oca`, report `instances[1].transform[6]` and the governing schema title.
S05-Q003. Check `examples/bracket_stress_result.ocr` against its schema: what is `bufferViews[1].name`, and which schema title applies?
S05-Q004. Trace `inst_bracket_01` across the assembly reference. Which source file is used, and what is the referenced file's `uct[0].params.primitives[0].center[0]`?
S05-Q005. When the validator checks `.oce`, which schema file is selected and what header version should pass?
S05-Q006. Map `.ocr` from README to schemas: what name and title should a reviewer cite?
S05-Q007. What is `instances[1].transform[14]` in `examples/assembly_demo.oca`, and what OpenCAD schema title covers that file extension?
S05-Q008. Pair the sample value and schema: for `examples/bracket_stress_test.ocs`, give `target.source_uri` plus the schema title.
S05-Q009. Pair the sample value and schema: for `examples/bracket_stress_result.ocr`, give `bufferViews[2].byteOffset` plus the schema title.
S05-Q010. For instance `inst_bracket_01`, connect the assembly source URI to the referenced artifact and report `uct[1].op_id`.
S05-Q011. What file does `inst_sensor_01` in `examples/assembly_demo.oca` reference, and what value does that file give for `nets[0].name`?
S05-Q012. For `.ocr` data in `examples/bracket_stress_result.ocr`, report `bufferViews[1].byteLength` and the governing schema title.
S05-Q013. For result field `Von_Mises_Stress`, connect the field data index to the buffer view and backing buffer URI.
S05-Q014. For `.oca` data in `examples/assembly_demo.oca`, report `instances[1].transform[12]` and the governing schema title.
S05-Q015. Check `examples/wiring_demo.oce` against its schema: what is `components[0].ref_des`, and which schema title applies?
S05-Q016. Use the example and schema together: `examples/bracket_stress_result.ocr` has what `bufferViews[0].name` value, and under what schema title?
S05-Q017. When validating `.oca` content, what README domain name and schema title must be connected?
S05-Q018. Pair the sample value and schema: for `examples/bracket_stress_test.ocs`, give `setup.loads[1].type` plus the schema title.
S05-Q019. For `.oce` data in `examples/wiring_demo.oce`, report `components[2].ref_des` and the governing schema title.
S05-Q020. Resolve this across repository policy files: which license applies to `specification/` files, and which contribution rule repeats that license for specification changes?
S05-Q021. Check `examples/bracket_stress_result.ocr` against its schema: what is `buffers[0].uri`, and which schema title applies?
S05-Q022. Use the example and schema together: `examples/bracket_stress_result.ocr` has what `bufferViews[0].type` value, and under what schema title?
S05-Q023. For the OpenCAD example `examples/bracket_stress_result.ocr`, identify `fields[0].data` and the matching schema title.
S05-Q024. Which simulation does `examples/bracket_stress_result.ocr` cite, and what load type is declared for `load_gravity` in that simulation?
S05-Q025. What does README call `.ocp`, and what is the title field in its schema?
S05-Q026. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `header.version` plus the schema title.
S05-Q027. Use the example and schema together: `examples/bracket_demo.ocp` has what `header.version` value, and under what schema title?
S05-Q028. What does README call `.oca`, and what is the title field in its schema?
S05-Q029. When validating `examples/bracket_stress_test.ocs`, what does `setup.loads[1].vector[1]` contain and what schema title should be used?
S05-Q030. In `examples/bracket_stress_result.ocr`, what value is stored at `bufferViews[2].byteLength`, and what is the schema title for `.ocr`?
S05-Q031. From `examples/assembly_demo.oca`, use `inst_sensor_01` to find its source URI, then give `components[1].part_number` from that source.
S05-Q032. When validating `examples/assembly_demo.oca`, what does `instances[1].source_uri` contain and what schema title should be used?
S05-Q033. Use the example and schema together: `examples/bracket_demo.ocp` has what `metadata.units` value, and under what schema title?
S05-Q034. From `examples/assembly_demo.oca`, use `inst_sensor_01` to find its source URI, then give `nets[0].name` from that source.
S05-Q035. Which required repository files does the validator check for documentation, and which README status line names the normative draft file?
S05-Q036. Map `.ocs` from README to schemas: what name and title should a reviewer cite?
S05-Q037. Trace `inst_sensor_01` across the assembly reference. Which source file is used, and what is the referenced file's `nets[0].nodes[1]`?
S05-Q038. What file does `inst_bracket_01` in `examples/assembly_demo.oca` reference, and what value does that file give for `uct[2].type`?
S05-Q039. Pair the sample value and schema: for `examples/bracket_demo.ocp`, give `uct[1].params.direction[0]` plus the schema title.
S05-Q040. When the validator checks `.ocs`, which schema file is selected and what header version should pass?
S05-Q041. Use the example and schema together: `examples/bracket_demo.ocp` has what `uct[0].params.primitives[0].center[0]` value, and under what schema title?
S05-Q042. For the OpenCAD example `examples/bracket_stress_test.ocs`, identify `results.status` and the matching schema title.
S05-Q043. Resolve this across repository policy files: who is the current maintainer, and which governance section points readers to the maintainer list?
S05-Q044. For the OpenCAD example `examples/bracket_stress_test.ocs`, identify `setup.loads[1].vector[2]` and the matching schema title.
S05-Q045. What does the simulation target point at, and what is the target assembly's `metadata.assembly_name`?
S05-Q046. Follow assembly instance `inst_bracket_01` from `examples/assembly_demo.oca`. What source URI does it use, and what `uct[1].params.direction[0]` value is in the referenced file?
S05-Q047. Pair the sample value and schema: for `examples/assembly_demo.oca`, give `instances[0].transform[14]` plus the schema title.
S05-Q048. For a production standards review, who is the current maintainer, and which governance section points readers to the maintainer list?
S05-Q049. Cross-reference the validation script and VERSION: what schema path and expected version apply to `.ocs`?
S05-Q050. Using both cited governance/licensing artifacts, which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?
