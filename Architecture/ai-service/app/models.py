from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NonEmptyString = Annotated[str, Field(min_length=1)]
EntityType = Literal["CLASS", "INTERFACE", "COMPONENT"]
SpringType = Literal["CONTROLLER", "SERVICE", "REPOSITORY", "COMPONENT", "CONFIGURATION", "NONE"]
RelationshipType = Literal["DEPENDS_ON", "CALLS", "IMPORTS", "EXTENDS", "IMPLEMENTS", "CONTAINS"]


class ArchitectureModel(BaseModel):
    # Reject unknown fields and coercion so a mismatched context is reported instead of partly accepted.
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceLocation(ArchitectureModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def check_line_order(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be at or after start_line.")
        return self


class ComponentInfo(ArchitectureModel):
    name: NonEmptyString
    entity_type: EntityType
    spring_type: SpringType
    package: str
    file_path: NonEmptyString
    annotations: list[NonEmptyString]
    source_location: SourceLocation

    @field_validator("annotations")
    @classmethod
    def check_unique_annotations(cls, annotations: list[str]) -> list[str]:
        if len(annotations) != len(set(annotations)):
            raise ValueError("Annotation names must be unique.")
        return annotations


class RelationshipInfo(ArchitectureModel):
    source: NonEmptyString
    target: NonEmptyString
    relationship: RelationshipType
    source_location: SourceLocation | None = None

    @field_validator("source_location", mode="before")
    @classmethod
    def check_present_location(cls, location: object) -> object:
        # The shared schema allows an omitted location, but not an explicit JSON null.
        if location is None:
            raise ValueError("Omit source_location when its location is unknown.")
        return location


class ProjectContext(ArchitectureModel):
    schema_version: Literal["1.0"]
    project_name: NonEmptyString
    project_root: NonEmptyString
    components: list[ComponentInfo]
    relationships: list[RelationshipInfo]


class ProjectContextSyncResponse(ArchitectureModel):
    updated: bool
    project_name: NonEmptyString
    components: int = Field(ge=0)
    relationships: int = Field(ge=0)
    rag_invalidated: bool
