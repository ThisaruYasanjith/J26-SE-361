package org.j26.architecture.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.List;

@JsonPropertyOrder({"schema_version", "project_name", "project_root", "components", "relationships"})
public record ProjectContext(
        @JsonProperty("schema_version") String schemaVersion,
        @JsonProperty("project_name") String projectName,
        @JsonProperty("project_root") String projectRoot,
        List<ComponentInfo> components,
        List<RelationshipInfo> relationships) {

    public ProjectContext {
        components = List.copyOf(components);
        relationships = List.copyOf(relationships);
    }
}
