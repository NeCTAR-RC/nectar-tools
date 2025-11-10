#!/bin/bash

#############################################
# VIP Health Check Script
# Performs connectivity and SSL cert checks
#############################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration - Set your VIP domains via environment variables
# If not set, those checks will be skipped
PA_VIP_DOMAIN="${PA_VIP_DOMAIN}"
PU_VIP_DOMAIN="${PU_VIP_DOMAIN}"

# SSL cert warning/critical thresholds (days)
SSL_WARNING_DAYS=30
SSL_CRITICAL_DAYS=15

# Output file
OUTPUT_FILE="vip_check_results_$(date +%Y%m%d_%H%M%S).log"

#############################################
# Helper Functions
#############################################

print_header() {
    echo -e "\n${YELLOW}========================================${NC}"
    echo -e "${YELLOW}$1${NC}"
    echo -e "${YELLOW}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "$1"
}

#############################################
# Check Functions
#############################################

check_ping() {
    local host=$1
    local name=$2

    print_info "Checking ping to $name ($host)..."
    if ping -c 3 -W 2 "$host" &>/dev/null; then
        print_success "$name is pingable"
        return 0
    else
        print_error "$name is NOT pingable"
        return 1
    fi
}

check_port() {
    local host=$1
    local port=$2
    local service=$3

    print_info "Checking $service port $port on $host..."
    if timeout 5 bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
        print_success "$service port $port is reachable"
        return 0
    else
        print_error "$service port $port is NOT reachable"
        return 1
    fi
}

check_port_nc() {
    local host=$1
    local port=$2
    local service=$3

    print_info "Checking $service with netcat..."
    if nc -v -w 3 -z "$host" "$port" 2>&1 | grep -q "succeeded\|open"; then
        print_success "NC: $service port $port is open"
        return 0
    else
        print_error "NC: $service port $port connection failed"
        return 1
    fi
}

check_ssl_cert() {
    local host=$1
    local port=$2
    local protocol=$3
    local service=$4

    print_info "Checking SSL certificate for $service on $host:$port..."

    # Check if nagios check_ssl_cert plugin exists
    if [ ! -f "/usr/lib/nagios/plugins/check_ssl_cert" ]; then
        print_error "Nagios check_ssl_cert plugin not found at /usr/lib/nagios/plugins/check_ssl_cert"
        print_info "Falling back to openssl check..."

        # Fallback to openssl
        local cert_info
        if [ "$protocol" = "mysql" ]; then
            cert_info=$(timeout 5 openssl s_client -connect "$host:$port" -starttls mysql </dev/null 2>/dev/null | openssl x509 -noout -dates 2>/dev/null)
        else
            cert_info=$(timeout 5 openssl s_client -connect "$host:$port" </dev/null 2>/dev/null | openssl x509 -noout -dates 2>/dev/null)
        fi

        if [ -n "$cert_info" ]; then
            print_success "SSL certificate found for $service"
            echo "$cert_info" | sed 's/^/  /'
            return 0
        else
            print_error "Failed to retrieve SSL certificate for $service"
            return 1
        fi
    else
        # Use nagios plugin
        local cmd="/usr/lib/nagios/plugins/check_ssl_cert -H $host --port $port -w $SSL_WARNING_DAYS -c $SSL_CRITICAL_DAYS"
        [ "$protocol" = "mysql" ] && cmd="$cmd --protocol mysql"

        local output
        output=$($cmd 2>&1)
        local result=$?

        if [ $result -eq 0 ]; then
            print_success "SSL cert OK for $service"
            echo "$output" | sed 's/^/  /'
            return 0
        elif [ $result -eq 1 ]; then
            print_error "SSL cert WARNING for $service"
            echo "$output" | sed 's/^/  /'
            return 1
        else
            print_error "SSL cert CRITICAL or ERROR for $service"
            echo "$output" | sed 's/^/  /'
            return 2
        fi
    fi
}

#############################################
# Main Execution
#############################################

main() {
    print_header "VIP Health Check Script"
    echo "Start Time: $(date)"

    # Check if any domains are configured
    if [ -z "$PA_VIP_DOMAIN" ] && [ -z "$PU_VIP_DOMAIN" ]; then
        print_error "No VIP domains configured!"
        echo "Please set PA_VIP_DOMAIN and/or PU_VIP_DOMAIN environment variables"
        echo "Example: PA_VIP_DOMAIN=pa.example.com PU_VIP_DOMAIN=pu.example.com $0"
        exit 1
    fi

    [ -n "$PA_VIP_DOMAIN" ] && echo "PA VIP Domain: $PA_VIP_DOMAIN" || echo "PA VIP Domain: Not configured (skipping PA checks)"
    [ -n "$PU_VIP_DOMAIN" ] && echo "PU VIP Domain: $PU_VIP_DOMAIN" || echo "PU VIP Domain: Not configured (skipping PU checks)"
    echo "Results will be saved to: $OUTPUT_FILE"
    echo ""

    # Track overall results
    total_checks=0
    failed_checks=0

    #############################################
    # PA VIP Checks
    #############################################
    if [ -n "$PA_VIP_DOMAIN" ]; then
        print_header "PA VIP Connectivity Checks"

        ((total_checks++))
        check_ping "$PA_VIP_DOMAIN" "PA VIP" || ((failed_checks++))

        ((total_checks++))
        check_port "$PA_VIP_DOMAIN" 3306 "PA VIP DB" || ((failed_checks++))

        ((total_checks++))
        check_port "$PA_VIP_DOMAIN" 5671 "PA VIP MQ" || ((failed_checks++))

        # Netcat checks
        ((total_checks++))
        check_port_nc "$PA_VIP_DOMAIN" 3306 "PA VIP DB" || ((failed_checks++))

        ((total_checks++))
        check_port_nc "$PA_VIP_DOMAIN" 5671 "PA VIP MQ" || ((failed_checks++))

        # SSL Certificate Checks
        print_header "PA VIP SSL Certificate Checks"

        ((total_checks++))
        check_ssl_cert "$PA_VIP_DOMAIN" 3306 "mysql" "PA VIP DB" || ((failed_checks++))

        ((total_checks++))
        check_ssl_cert "$PA_VIP_DOMAIN" 5671 "" "PA VIP MQ" || ((failed_checks++))
    else
        print_header "PA VIP Checks"
        print_info "PA_VIP_DOMAIN not set - skipping PA checks"
    fi

    #############################################
    # PU VIP Checks
    #############################################
    if [ -n "$PU_VIP_DOMAIN" ]; then
        print_header "PU VIP Connectivity Checks"

        ((total_checks++))
        check_ping "$PU_VIP_DOMAIN" "PU VIP" || ((failed_checks++))

        ((total_checks++))
        check_port "$PU_VIP_DOMAIN" 443 "PU VIP NoVNC" || ((failed_checks++))

        ((total_checks++))
        check_port "$PU_VIP_DOMAIN" 9292 "PU VIP Glance" || ((failed_checks++))

        # Netcat checks
        ((total_checks++))
        check_port_nc "$PU_VIP_DOMAIN" 443 "PU VIP NoVNC" || ((failed_checks++))

        ((total_checks++))
        check_port_nc "$PU_VIP_DOMAIN" 9292 "PU VIP Glance" || ((failed_checks++))

        # SSL Certificate Checks
        print_header "PU VIP SSL Certificate Checks"

        ((total_checks++))
        check_ssl_cert "$PU_VIP_DOMAIN" 443 "" "PU VIP NoVNC" || ((failed_checks++))

        ((total_checks++))
        check_ssl_cert "$PU_VIP_DOMAIN" 9292 "" "PU VIP Glance" || ((failed_checks++))
    else
        print_header "PU VIP Checks"
        print_info "PU_VIP_DOMAIN not set - skipping PU checks"
    fi

    #############################################
    # Summary
    #############################################
    print_header "Summary"
    echo "End Time: $(date)"
    echo "Total Checks: $total_checks"
    echo "Passed: $((total_checks - failed_checks))"
    echo "Failed: $failed_checks"

    if [ $failed_checks -eq 0 ]; then
        print_success "All checks passed!"
        exit 0
    else
        print_error "$failed_checks check(s) failed"
        exit 1
    fi
}

# Execute main function and tee output to file
main 2>&1 | tee "$OUTPUT_FILE"
