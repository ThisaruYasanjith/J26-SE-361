package lk.sliit.codecleanliness;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class JavaSourceParserTest {

    @Test
    void shouldParseValidJavaClass() {

        String source = """
                public class Sample {
                    public void greet() {
                        System.out.println("Hello");
                    }
                }
                """;

        JavaSourceParser parser = new JavaSourceParser();
        CompilationUnit unit = parser.parse(source);

        assertEquals(
                1,
                unit.findAll(ClassOrInterfaceDeclaration.class).size()
        );

        assertEquals(
                "Sample",
                unit.findFirst(ClassOrInterfaceDeclaration.class)
                        .orElseThrow()
                        .getNameAsString()
        );
    }

    @Test
    void shouldRejectEmptySourceCode() {

        JavaSourceParser parser = new JavaSourceParser();

        assertThrows(
                IllegalArgumentException.class,
                () -> parser.parse("")
        );
    }

    @Test
    void shouldRejectInvalidJavaSyntax() {

        JavaSourceParser parser = new JavaSourceParser();

        assertThrows(
                IllegalArgumentException.class,
                () -> parser.parse("public class {")
        );
    }
}