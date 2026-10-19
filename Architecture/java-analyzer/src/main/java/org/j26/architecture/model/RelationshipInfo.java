package org.j26.architecture.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

public record RelationshipInfo(
        String source,
        String target,
        RelationshipType relationship,
        @JsonProperty("source_location")
        @JsonInclude(JsonInclude.Include.NON_NULL) SourceLocation sourceLocation) {
}
