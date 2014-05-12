#!/bin/bash
## Monash: This will generate local usage report base on univeristy domain (sort from user email address)
## top 10 projects
## top 10 users

#1        2       3        4     5      6        7     8      9        10
#uuid,user_id,project_id,Create,Delete,Duration,Usage,vcpus,memory_mb,host

echo "Enter Report Start Date (Format example: 2014-01-01)"
read SDAY_INPUT
sday=$SDAY_INPUT
echo "Enter Report End Date (Format example: 2014-01-31)"
read EDAY_INPUT
eday=$EDAY_INPUT
month=$sday-$eday

#nodes=52
#cpn=44

ddir=/home/saung/report/$month

report=$month.report.csv

CMD="/usr/bin/mysql -e"
DB=nova_monash_01

if [ ! -d "$ddir" ]; then mkdir -p $ddir;fi
cd $ddir

$CMD "use $DB;select uuid, user_id, project_id,
    UNIX_TIMESTAMP(IF(created_at < '$sday 00:00:00','$sday 00:00:00',created_at)) as 'Create_at',
    UNIX_TIMESTAMP(IF(deleted_at >= '$eday 23:59:59','$eday 23:59:59',COALESCE(deleted_at,'$eday 23:59:59'))) as 'Delete_at',
    vcpus, memory_mb, host

    from instances
    where
    (created_at BETWEEN '$sday 00:00:00' AND '$eday 23:59:59')
        OR (created_at < '$sday 00:00:00' AND deleted_at BETWEEN '$sday 00:00:00' AND '$eday 23:59:59')
        OR (created_at < '$sday 00:00:00' AND deleted_at IS NULL)
        OR (created_at < '$sday 00:00:00' AND deleted_at > '$eday 23:59:59') "| tr '\t' ', ' > $month.csv


cat $month.csv| tail -n+2 > $month.rawdata
#cat sample.csv| tail -n+2 > $month.rawdata
 
rawdata=$month.rawdata


#Total Number of compute nodes
ss=`date +%s --date="$sday 00:00:00"`
es=`date +%s --date="$eday 23:59:59"`
ts=`echo "$es - $ss"|bc -l`
#echo $ts

#availhr=`echo "scale=3;$nodes * $cpn * $ts / 3600" | bc -l`
#echo availablehr
#echo $availhr
#echo "" 

#usagehr=`cat $rawdata |awk -F, 'OFMT = "%.03f" {total+=($5-$4)*$6} END {print total/3600}'`
#echo usagehr
#echo $usagehr
#echo ""

#usagepc=`echo "scale=3;$usagehr / $availhr * 100"| bc -l`
#echo usagepc
#echo $usagepc
#echo ""

tinst=`cat $month.rawdata |wc -l`
tcpus=`awk -F, '{tcore+=$6} END {print tcore}' $month.rawdata`

echo Report from $sday to $eday,,, > $report
#echo "Available hour(48 compute x 44 cpus),Usage hour, Usage Percentage,Total Instances,Total CPUs" >> $report
#echo $availhr,$usagehr,$usagepc,$tinst,$tcpus >> $report
#echo "" >> $report

userids=$month.userids
projectids=$month.projectids

cat $rawdata |awk -F, '{print $2}' |sort -u > $userids 
cat $rawdata |awk -F, '{print $3}' |sort -u > $projectids 

user_usage=$month.user.usage

for i in `cat $userids`;do 
    awk -v x=$i -F, '$2 == x {s+=($5-$4)*$6;inst++;vcpu+=$6} END {print x","s/3600","inst","vcpu}' $rawdata
done > $user_usage

project_usage=$month.project.usage

for i in `cat $projectids`;do
    awk -v x=$i -F, '$3 == x {s+=($5-$4)*$6;inst++;vcpu+=$6} END {print x","s/3600","inst","vcpu}' $rawdata
done > $project_usage

export OS_AUTH_URL=https://keystone.rc.nectar.org.au:5000/v2.0/
export OS_NO_CACHE=true
export OS_TENANT_NAME=admin
echo "Please enter your OpenStack Username(admin credential): "
read -s OS_USERNAME_INPUT
export OS_USERNAME=$OS_USERNAME_INPUT
echo "Please enter your OpenStack Password(admin credential): "
read -s OS_PASSWORD_INPUT
export OS_PASSWORD=$OS_PASSWORD_INPUT

keystone user-list > keystone.user-list
keystone tenant-list > keystone.project-list

# Get username from keystone
function get_name_uni () {
    for i in `cat $1`;do
    usid=`echo $i |awk -F, '{print $1}'` 
    nama=`cat keystone.user-list|grep -w $usid |awk '{print $4}'`
    uni=`echo $nama | awk -F@ '{print $2}'`
    echo $i,$nama,$uni
    done
}    

# Get top 15
function get_top15 () {
    cat $1 |sort -s -g -t "," -r -k2 | head -n 15
}

get_name_uni $user_usage > $user_usage.tmp && mv $user_usage.tmp $user_usage 

topuser_usage=$month.topuser.usage
get_top15 $user_usage > $topuser_usage

uni_usage=$month.uni.usage
for i in `awk -F, '{print $6}' $user_usage|sort -u`;do 
    awk -F, -v x=$i '$6==x {s+=$2;tinst+=$3;tvcpu+=$4} END {print x","s","tinst","tvcpu}' $user_usage;
done > $uni_usage

topuni_usage=$month.topuni.usage
cat $uni_usage |sort -s -g -t "," -r -k2 > $topuni_usage

for i in `cat $project_usage`;do
    prid=`echo $i | awk -F, '{print $1}'`
    prnama=`cat keystone.project-list |awk -v x=$prid '$2==x {print $4}'`
    echo $i,$prnama
    done > $project_usage.tmp
   
topproject_usage=$month.topproject.usage
get_top15 $project_usage.tmp > $topproject_usage


echo "Institute(Desc order),Usage Hour,Instances,CPUs" >> $report
cat $topuni_usage >> $report 
echo "" >> $report

echo "Project(Top10),Usage Hour,Instances, CPUs" >> $report
head -n 10 $topproject_usage | awk -F, '{print $5","$2","$3","$4}' >> $report
echo "" >> $report

echo "User(Top10),Usage Hour,Instances,CPUs" >> $report
head -n 10 $topuser_usage  |awk -F, '{print $5","$2","$3","$4}' >> $report
echo "" >> $report
