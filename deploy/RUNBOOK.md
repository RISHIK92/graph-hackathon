# Deploy runbook (item 21)

One Ubuntu 24.04 VM (t3.medium, 30 GB gp3) in ap-south-1, behind an Elastic IP, running
`deploy/docker-compose.prod.yml`: Caddy (80/443, automatic HTTPS) in front of the UI and the API; FalkorDB 6.0.1
with no host port. A t3.medium costs roughly $1 a day while it runs (plus the Elastic IP while it is attached).

## 1. AWS (profile `rishik-personal`, region ap-south-1, every resource tagged `project=company-brain`)

Run this block in **bash** (`bash`, then paste): zsh doesn't split `$P` into words.

```bash
P="--profile rishik-personal --region ap-south-1"
TAG='ResourceType=%s,Tags=[{Key=project,Value=company-brain}]'
AMI=$(aws ssm get-parameter $P --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --query Parameter.Value --output text)
MYIP=$(curl -s https://checkip.amazonaws.com)
aws ec2 create-key-pair $P --key-name company-brain-key --key-type ed25519 --query KeyMaterial --output text \
  --tag-specifications "$(printf "$TAG" key-pair)" > ~/.ssh/company-brain-key.pem && chmod 600 ~/.ssh/company-brain-key.pem
SG=$(aws ec2 create-security-group $P --group-name company-brain-web --description "company-brain: 80/443 public, 22 from one IP" \
  --tag-specifications "$(printf "$TAG" security-group)" --query GroupId --output text)
aws ec2 authorize-security-group-ingress $P --group-id $SG --ip-permissions \
  "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}]" \
  "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]" \
  "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MYIP/32}]"
ID=$(aws ec2 run-instances $P --image-id $AMI --instance-type t3.medium --key-name company-brain-key \
  --security-group-ids $SG --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications "$(printf "$TAG" instance)" "$(printf "$TAG" volume)" --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running $P --instance-ids $ID
EIP=$(aws ec2 allocate-address $P --domain vpc --tag-specifications "$(printf "$TAG" elastic-ip)" --query AllocationId --output text)
aws ec2 associate-address $P --instance-id $ID --allocation-id $EIP
aws ec2 describe-addresses $P --allocation-ids $EIP --query 'Addresses[0].PublicIp' --output text
```

Your IP changes? Replace the port 22 rule (`revoke-security-group-ingress`, then authorize the new `/32`).

## 2. DNS

Add an **A record** for the subdomain (never the apex `rishiklabs.tech`, which serves another site) pointing at
the Elastic IP, at Namify's DNS. Wait until `dig +short <subdomain>` returns the Elastic IP; Caddy requests the
certificate on first start and retries until DNS resolves.

## 3. First boot

```bash
# from your machine: the code goes over as a git bundle (nothing needs pushing)
git bundle create /tmp/company-brain.bundle main
scp -i ~/.ssh/company-brain-key.pem /tmp/company-brain.bundle ubuntu@<elastic-ip>:
ssh -i ~/.ssh/company-brain-key.pem ubuntu@<elastic-ip>
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker ubuntu && exit   # log in again after this
git clone company-brain.bundle graph-hackathon && cd graph-hackathon
cp deploy/.env.prod.example deploy/.env
sed -i "s/^BRAIN_DOMAIN=.*/BRAIN_DOMAIN=<subdomain>/" deploy/.env
sed -i "s/^PUBLIC_WRITE_TOKEN=.*/PUBLIC_WRITE_TOKEN=$(openssl rand -hex 24)/" deploy/.env
sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 24)/" deploy/.env
nano deploy/.env        # paste the OpenRouter demo key into OPENROUTER_API_KEY yourself
chmod 600 deploy/.env
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml exec api brain reset --seed world/seeds/1    # seed the graph
```

Read the judges' token on the VM only (`grep PUBLIC_WRITE_TOKEN deploy/.env`); never paste it into chat or git.

## 4. Check

From your machine: `deploy/smoke.sh https://<subdomain>` (health, a cited answer, an anonymous write refused,
the token check, TLS). Then confirm only 22/80/443 answer from outside:
`for p in 22 80 443 3000 6379 8000; do nc -z -w 3 <elastic-ip> $p && echo "$p open" || echo "$p closed"; done`.

## 5. Logs

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f --tail 100 api     # or ui, caddy, falkordb
docker compose -f deploy/docker-compose.prod.yml ps
```

## 6. Rollback

```bash
git fetch ~/company-brain.bundle main && git log --oneline -5 FETCH_HEAD   # a newer bundle, scp'd as above
git checkout <commit>
docker compose -f deploy/docker-compose.prod.yml up -d --build api ui
```

The graph lives in the `falkor-data` volume; `brain reset` rebuilds it from seed 1 at any time.

## 7. Reset schedule

`BRAIN_SCHEDULED_RESET=on` with `BRAIN_RESET_EVERY_MIN=1440`: the API resets the graph to seed 1 every 24 hours
from its start, deferred while a token session was active in the last 30 minutes (forced after 6 hours).
`GET /api/health` shows `next_reset_at`. A manual reset: `POST /api/admin/reset` with the admin token.

## 8. Limits

`BRAIN_TURNS_PER_IP_HOUR` (60) per client IP; anonymous sessions also 20 turns per 10 minutes; token writes 30 an
hour. `BRAIN_LLM_DAILY_CAP` (3000) model requests per UTC day, after which answers come from the graph's own
deterministic path until the next day. The OpenRouter key's own limit (about $5) is the last stop.

## 9. Stop it after the hackathon

```bash
P="--profile rishik-personal --region ap-south-1"
aws ec2 stop-instances $P --instance-ids <id>            # stops the hourly instance cost; the disk remains (~$2.40/month)
aws ec2 release-address $P --allocation-id <eip-alloc>   # an idle Elastic IP is billed hourly
aws ec2 terminate-instances $P --instance-ids <id>       # removes the VM and its disk
```
