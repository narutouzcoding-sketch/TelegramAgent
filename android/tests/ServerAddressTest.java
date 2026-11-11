package uz.telegramagent.mobile;

public class ServerAddressTest {
    public static void main(String[] args) {
        check(ServerAddress.validate("10.10.0.251:8765").equals("http://10.10.0.251:8765/"));
        check(ServerAddress.validate("agent.example.com").equals("https://agent.example.com/"));
        check(ServerAddress.sameOrigin("https://agent.example.com/", "https://agent.example.com:443/api/state"));
        check(!ServerAddress.sameOrigin("https://agent.example.com/", "https://attacker.example/api/state"));
        check(!ServerAddress.sameOrigin("https://agent.example.com/", "http://agent.example.com/"));
        for (String value : new String[]{"http://example.com", "file:///etc/passwd", "javascript:alert(1)",
             "http://010.1.1.1", "https://user:password@example.com", "https://example.com/path", "https://example.com/?key=secret"}) {
            boolean rejected = false;
            try { ServerAddress.validate(value); }
            catch (IllegalArgumentException error) { rejected = true; }
            check(rejected);
        }
        System.out.println("Server address validation and origin tests passed.");
    }
    private static void check(boolean condition) { if (!condition) throw new AssertionError(); }
}
