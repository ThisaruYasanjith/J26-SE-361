package org.j26.architecture.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SourceLocation(
        @JsonProperty("start_line") int startLine,
        @JsonProperty("end_line") int endLine) {

    public SourceLocation {
        if (startLine < 1 || endLine < startLine) {
            throw new IllegalArgumentException("Source lines must be positive and end at or after the start.");
        }
    }
}
