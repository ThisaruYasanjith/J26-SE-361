package org.j26.architecture;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.javaparser.ast.CompilationUnit;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.EntityType;
import org.j26.architecture.model.SourceLocation;
import org.j26.architecture.model.SpringType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ArchitectureEntityExtractorTest {
    @TempDir
    Path project;

    private final JavaProjectScanner scanner = new JavaProjectScanner();

    @Test
    void extractsTopLevelClassesInterfacesAndTheirPackage() throws IOException {
        List<ComponentInfo> components = scanSource("""
                package com.example.architecture.service;
                public class PaymentService {}
                interface PaymentGateway {}
                """);

        assertEquals(2, components.size());
        assertEquals("com.example.architecture.service.PaymentService", components.get(0).name());
        assertEquals(EntityType.CLASS, components.get(0).entityType());
        assertEquals("com.example.architecture.service.PaymentGateway", components.get(1).name());
        assertEquals(EntityType.INTERFACE, components.get(1).entityType());
        assertEquals("com.example.architecture.service", components.get(0).packageName());
        assertEquals("com.example.architecture.service", components.get(1).packageName());
    }

    @Test
    void usesAnEmptyPackageForDefaultPackageDeclarations() throws IOException {
        ComponentInfo component = scanSource("class DefaultPackageClass {}").get(0);

        assertEquals("DefaultPackageClass", component.name());
        assertEquals("", component.packageName());
        assertEquals(SpringType.NONE, component.springType());
        assertTrue(component.annotations().isEmpty());
    }

    @ParameterizedTest
    @CsvSource({
            "RestController, CONTROLLER",
            "Controller, CONTROLLER",
            "Service, SERVICE",
            "Repository, REPOSITORY",
            "Component, COMPONENT",
            "Configuration, CONFIGURATION",
            "org.springframework.web.bind.annotation.RestController, CONTROLLER",
            "org.springframework.stereotype.Controller, CONTROLLER",
            "org.springframework.stereotype.Service, SERVICE",
            "org.springframework.stereotype.Repository, REPOSITORY",
            "org.springframework.stereotype.Component, COMPONENT",
            "org.springframework.context.annotation.Configuration, CONFIGURATION"
    })
    void recognizesSimpleAndQualifiedSpringStereotypes(String annotation, SpringType expected) throws IOException {
        ComponentInfo component = scanSource("@" + annotation + " class Example {}").get(0);

        assertEquals(expected, component.springType());
        assertEquals(EntityType.CLASS, component.entityType());
        assertEquals(List.of(annotation), component.annotations());
    }

    @Test
    void keepsAllAnnotationNamesAndDeduplicatesRepeatedNames() throws IOException {
        ComponentInfo component = scanSource("""
                @Tag("first")
                @Tag("second")
                @Service
                @Deprecated
                class PaymentService {}
                """).get(0);

        assertEquals(List.of("Tag", "Service", "Deprecated"), component.annotations());
        assertEquals(SpringType.SERVICE, component.springType());
    }

    @Test
    void preservesInterfaceKindForASpringRepository() throws IOException {
        ComponentInfo component = scanSource("@Repository interface OrderRepository {}").get(0);

        assertEquals(EntityType.INTERFACE, component.entityType());
        assertEquals(SpringType.REPOSITORY, component.springType());
    }

    @Test
    void doesNotInferSpringTypesFromPackagesOrUnrelatedQualifiedAnnotations() throws IOException {
        List<ComponentInfo> components = scanSource("""
                package demo.service;
                @Deprecated class Plain {}
                @other.Service class CustomAnnotated {}
                """);

        assertEquals(SpringType.NONE, components.get(0).springType());
        assertEquals(List.of("Deprecated"), components.get(0).annotations());
        assertEquals(SpringType.NONE, components.get(1).springType());
        assertEquals(List.of("other.Service"), components.get(1).annotations());
    }

    @Test
    void recognizesAMisplacedServiceFromItsAnnotation() throws IOException {
        write("src/main/java/demo/controller/MisplacedAuditService.java", """
                package demo.controller;
                @Service class MisplacedAuditService {}
                """);

        ComponentInfo component = scanner.scan(project).components().get(0);

        assertEquals(SpringType.SERVICE, component.springType());
        assertEquals("demo.controller", component.packageName());
        assertEquals("src/main/java/demo/controller/MisplacedAuditService.java", component.filePath());
    }

    @ParameterizedTest
    @CsvSource({"Component Service", "Service Component"})
    void specificStereotypesTakePrecedenceOverComponent(String annotationOrder) throws IOException {
        String annotations = "@" + annotationOrder.replace(" ", " @");
        ComponentInfo component = scanSource(annotations + " class PaymentService {}").get(0);

        assertEquals(SpringType.SERVICE, component.springType());
    }

    @Test
    void extractsDirectSuperclassAndImplementedInterfaceNames() throws IOException {
        ComponentInfo component = scanSource("""
                class PaymentService extends base.BaseService<String>
                        implements Auditable<String>, audit.Trackable {}
                """).get(0);

        assertEquals("base.BaseService", component.extendsClass());
        assertEquals(List.of("Auditable", "audit.Trackable"), component.implementedInterfaces());
        assertTrue(component.extendedInterfaces().isEmpty());
    }

    @Test
    void preservesInterfacesExtendedByAnInterface() throws IOException {
        ComponentInfo component = scanSource("""
                interface PaymentGateway extends Auditable, tracking.Trackable {}
                """).get(0);

        assertNull(component.extendsClass());
        assertTrue(component.implementedInterfaces().isEmpty());
        assertEquals(List.of("Auditable", "tracking.Trackable"), component.extendedInterfaces());
    }

    @Test
    void usesEmptyInheritanceValuesWhenNoneAreDeclared() throws IOException {
        ComponentInfo component = scanSource("class Plain {}").get(0);

        assertNull(component.extendsClass());
        assertTrue(component.implementedInterfaces().isEmpty());
        assertTrue(component.extendedInterfaces().isEmpty());
    }

    @Test
    void usesOneBasedInclusiveDeclarationLines() throws IOException {
        ComponentInfo component = scanSource("package demo;\n\n@Service\npublic class PaymentService {\n}\n").get(0);

        assertEquals(new SourceLocation(3, 5), component.sourceLocation());
    }

    @Test
    void storesOnlyNormalizedProjectRelativePaths() throws IOException {
        write("src/main/java/demo/PaymentService.java", "package demo; class PaymentService {}");

        ComponentInfo component = scanner.scan(project.resolve("unused/..")).components().get(0);

        assertEquals("src/main/java/demo/PaymentService.java", component.filePath());
        assertFalse(Path.of(component.filePath()).isAbsolute());
        assertFalse(component.filePath().contains("\\"));
        assertFalse(component.filePath().contains(project.toString()));
    }

    @Test
    void ignoresNestedClassesAndOtherDeclarationKindsForNow() throws IOException {
        List<ComponentInfo> components = scanSource("""
                class Outer { class Nested {} interface NestedApi {} }
                interface TopLevelApi {}
                enum State { READY }
                record Payment(String reference) {}
                @interface Marker {}
                """);

        assertEquals(List.of("Outer", "TopLevelApi"), components.stream().map(ComponentInfo::name).toList());
    }

    @Test
    void skipsAstDeclarationsWithoutRangesInsteadOfInventingLocations() {
        CompilationUnit generatedUnit = new CompilationUnit();
        generatedUnit.addClass("Generated");

        List<ComponentInfo> components = new ArchitectureEntityExtractor().extract(
                generatedUnit, project, project.resolve("Generated.java"));

        assertTrue(components.isEmpty());
    }

    @Test
    void rejectsInvalidSourceLineRanges() {
        assertThrows(IllegalArgumentException.class, () -> new SourceLocation(0, 1));
        assertThrows(IllegalArgumentException.class, () -> new SourceLocation(1, 0));
        assertThrows(IllegalArgumentException.class, () -> new SourceLocation(3, 2));
    }

    @Test
    void rejectsFilesOutsideTheAnalyzedRoot() {
        assertThrows(IllegalArgumentException.class, () -> new ArchitectureEntityExtractor().extract(
                new CompilationUnit(), project.resolve("nested"), project.resolve("Outside.java")));
    }

    @Test
    void distinguishesMatchingSimpleNamesInDifferentPackages() throws IOException {
        write("src/main/java/demo/one/PaymentService.java", "package demo.one; class PaymentService {}");
        write("src/main/java/demo/two/PaymentService.java", "package demo.two; class PaymentService {}");

        List<String> names = scanner.scan(project).components().stream().map(ComponentInfo::name).toList();

        assertEquals(List.of("demo.one.PaymentService", "demo.two.PaymentService"), names);
    }

    @Test
    void keepsComponentJsonFieldsAlignedWithTheSharedContract() throws IOException {
        ComponentInfo component = scanSource("""
                package demo;
                @Service class PaymentService extends BaseService implements Auditable {}
                """).get(0);

        // Check the mapping in memory; producing a project-context file belongs to a later commit.
        JsonNode json = new ObjectMapper().valueToTree(component);
        Set<String> fields = new HashSet<>();
        json.fieldNames().forEachRemaining(fields::add);

        assertEquals(Set.of("name", "entity_type", "spring_type", "package", "file_path", "annotations", "source_location"), fields);
        assertEquals("demo.PaymentService", json.get("name").asText());
        assertEquals("CLASS", json.get("entity_type").asText());
        assertEquals("SERVICE", json.get("spring_type").asText());
        assertEquals("demo", json.get("package").asText());
        assertEquals(2, json.get("source_location").get("start_line").asInt());
        assertEquals(2, json.get("source_location").get("end_line").asInt());
        assertEquals(2, json.get("source_location").size());
        assertFalse(Files.exists(project.resolve("project_context.json")));
    }

    @Test
    void cliPrintsTheSpringTypeDeclarationKindPackageAndRelativePath() throws IOException {
        write("src/main/java/demo/PaymentService.java", "package demo; @Service class PaymentService {}");
        ByteArrayOutputStream summary = new ByteArrayOutputStream();
        ByteArrayOutputStream errors = new ByteArrayOutputStream();

        try (PrintStream output = new PrintStream(summary, true, StandardCharsets.UTF_8);
             PrintStream errorOutput = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
            assertEquals(0, AnalyzerMain.run(new String[]{project.toString()}, output, errorOutput));
        }

        String text = summary.toString(StandardCharsets.UTF_8);
        assertTrue(text.contains("Architecture entities extracted: 1"));
        assertTrue(text.contains("SERVICE PaymentService (CLASS)"));
        assertTrue(text.contains("  package: demo"));
        assertTrue(text.contains("  file: src/main/java/demo/PaymentService.java"));
        assertEquals("", errors.toString(StandardCharsets.UTF_8));
    }

    private List<ComponentInfo> scanSource(String source) throws IOException {
        write("src/main/java/demo/Entities.java", source);
        return scanner.scan(project).components();
    }

    private Path write(String relativePath, String content) throws IOException {
        Path file = project.resolve(relativePath);
        Files.createDirectories(file.getParent());
        return Files.writeString(file, content, StandardCharsets.UTF_8);
    }
}
