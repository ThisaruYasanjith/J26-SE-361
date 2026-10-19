package org.j26.architecture.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Objects;

public record ComponentInfo(
        String name,
        @JsonProperty("entity_type") EntityType entityType,
        @JsonProperty("spring_type") SpringType springType,
        @JsonProperty("package") String packageName,
        @JsonProperty("file_path") String filePath,
        List<String> annotations,
        @JsonProperty("source_location") SourceLocation sourceLocation,
        // The context schema represents inheritance through relationships, not component fields.
        @JsonIgnore String extendsClass,
        @JsonIgnore List<String> implementedInterfaces,
        @JsonIgnore List<String> extendedInterfaces) {

    public ComponentInfo {
        annotations = List.copyOf(annotations);
        implementedInterfaces = List.copyOf(implementedInterfaces);
        extendedInterfaces = List.copyOf(extendedInterfaces);
        Objects.requireNonNull(sourceLocation, "An extracted entity needs a source range.");
    }
}
