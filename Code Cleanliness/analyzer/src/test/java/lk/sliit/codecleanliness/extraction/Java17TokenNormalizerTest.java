
package lk.sliit.codecleanliness.extraction;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Java17TokenNormalizerTest {

    private final JavaTokenNormalizer normalizer =
            new JavaTokenNormalizer();

    @Test
    void supportsJava17InstanceofPatternMatching() {

        String methodBody = """
                {
                    if (value instanceof String text) {
                        return text.length();
                    }
                    return 0;
                }
                """;

        List<String> tokens =
                normalizer.normalizeMethodBody(methodBody);

        assertFalse(tokens.isEmpty());
        assertTrue(tokens.contains("instanceof"));
        assertTrue(tokens.contains("IDENTIFIER"));
    }

    @Test
    void normalizesEquivalentJava17MethodBodies() {

        String first = """
                {
                    if (value instanceof String text) {
                        return text.length();
                    }
                    return 0;
                }
                """;

        String second = """
                {
                    if (object instanceof String name) {
                        return name.length();
                    }
                    return 0;
                }
                """;

        assertEquals(
                normalizer.normalizeMethodBody(first),
                normalizer.normalizeMethodBody(second)
        );
    }

    @Test
    void rejectsInvalidMethodBody() {

        assertThrows(
                IllegalArgumentException.class,
                () -> normalizer.normalizeMethodBody(
                        "{ if ( ) }"
                )
        );
    }
}
